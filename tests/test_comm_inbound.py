"""Offline tests for two-way comm — the inbound poller (receive leg).

No real network: the Telegram ``getUpdates`` long-poll and ``sendMessage`` both
go through injected recorders. Covers the security model: off-by-default, the
fail-closed sender allowlist, supervised-session spawning, and the durable offset
that dedupes across a restart.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from iron_jarvis.agents.orchestrator import Orchestrator
from iron_jarvis.comm import (
    InboundPoller,
    Notifier,
    TelegramChannel,
    build_notifier,
)
from iron_jarvis.comm.models import InboundOffsetRecord
from iron_jarvis.core.db import session_scope
from iron_jarvis.daemon.app import create_app


# --------------------------------------------------------------------------- #
# Fakes — a Telegram transport that honours the getUpdates offset semantics.
# --------------------------------------------------------------------------- #
class FakeTelegram:
    """Injected (url, params) transports for getUpdates (GET) + sendMessage (POST).

    Holds a list of pending updates; a ``getUpdates`` call with an ``offset``
    drops (confirms) every update with a lower id, exactly like the real API —
    so a persisted offset dedupes on the next poll.
    """

    def __init__(self, updates: list[dict[str, Any]]) -> None:
        self.updates = list(updates)
        self.sent: list[dict[str, Any]] = []
        self.poll_calls = 0

    # GET getUpdates
    def get(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        self.poll_calls += 1
        assert "getUpdates" in url
        offset = int(params.get("offset", 0) or 0)
        if offset:
            self.updates = [u for u in self.updates if u["update_id"] >= offset]
        return {"ok": True, "result": list(self.updates)}

    # POST sendMessage / sendChatAction (media uses multipart httpx — not this path)
    def post(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        if "sendChatAction" in url:
            self.sent.append({"_action": payload.get("action"), **payload})
            return {"status_code": 200, "ok": True}
        assert "sendMessage" in url or "sendPhoto" in url or "sendDocument" in url
        self.sent.append(payload)
        return {"status_code": 200}


def _update(update_id: int, sender: int, text: str, *, is_bot: bool = False) -> dict:
    return {
        "update_id": update_id,
        "message": {
            "text": text,
            "from": {"id": sender, "is_bot": is_bot},
            "chat": {"id": sender},
        },
    }


def _telegram(fake: FakeTelegram, config: dict[str, Any]) -> TelegramChannel:
    return TelegramChannel(
        config,
        http_post=fake.post,
        http_get=fake.get,
        secret_resolver=lambda n: "BOTTOKEN" if n == "tg_token" else None,
    )


def _poller(platform, channel: TelegramChannel) -> tuple[InboundPoller, Orchestrator]:
    notifier = Notifier()
    notifier.add_channel("tg", channel)
    orch = Orchestrator(platform)
    poller = InboundPoller(notifier, orch, platform.engine, event_bus=platform.event_bus)
    return poller, orch


# --------------------------------------------------------------------------- #
# OFF BY DEFAULT — no channels configured => poller does nothing, no network.
# --------------------------------------------------------------------------- #
def test_poller_disabled_with_no_channels(platform):
    notifier = build_notifier(None)  # the default => a single MockChannel
    poller = InboundPoller(notifier, Orchestrator(platform), platform.engine)
    assert poller.enabled() is False
    assert poller.inbound_channels() == []


def test_poller_disabled_until_inbound_explicitly_enabled(platform):
    fake = FakeTelegram([])
    # Configured + credentialed, but inbound NOT enabled => still off.
    ch = _telegram(fake, {"token_secret": "tg_token", "allowed_senders": [1]})
    poller, _ = _poller(platform, ch)
    assert poller.enabled() is False


def test_poller_skips_inbound_channel_without_credentials(platform):
    fake = FakeTelegram([])
    ch = TelegramChannel(
        {"token_secret": "tg_token", "inbound_enabled": True, "allowed_senders": [1]},
        http_post=fake.post,
        http_get=fake.get,
        secret_resolver=lambda n: None,  # token does NOT resolve
    )
    poller, _ = _poller(platform, ch)
    assert poller.enabled() is False  # opted in but no credentials => skipped


def test_daemon_boots_with_no_inbound_and_makes_no_channels(tmp_path):
    """A default daemon boot creates no inbound poller and no network."""
    from fastapi.testclient import TestClient

    with TestClient(create_app(str(tmp_path))) as client:
        assert client.get("/health").json()["status"] == "ok"
        # default comm => the mock channel only; nothing inbound-enabled.
        # (/comm/channels returns {name,type} objects so the UI can label/delete.)
        channels = client.get("/comm/channels").json()["channels"]
        assert [c["name"] for c in channels] == ["mock"]


# --------------------------------------------------------------------------- #
# AUTHORIZED sender => spawns ONE supervised session + replies the summary.
# --------------------------------------------------------------------------- #
async def test_authorized_sender_spawns_supervised_session_and_replies(platform):
    fake = FakeTelegram([_update(10, sender=777, text="do the thing")])
    ch = _telegram(
        fake,
        {"token_secret": "tg_token", "inbound_enabled": True, "allowed_senders": [777]},
    )
    poller, orch = _poller(platform, ch)
    assert poller.enabled() is True

    results = await poller.poll_once()

    assert len(results) == 1 and results[0]["status"] == "handled"
    sessions = orch.list_sessions()
    # Free-text uses BUILDER with a brand-aware task wrapper.
    assert any("do the thing" in (s.task or "") for s in sessions)
    root = next(s for s in sessions if "do the thing" in (s.task or ""))
    assert root.agent_type.value == "builder"
    # Ack ("Working on it…") + final summary; typing posts sendChatAction too.
    msg_texts = [s for s in fake.sent if s.get("text")]
    assert len(msg_texts) >= 2
    assert any("Working" in (s.get("text") or "") for s in msg_texts)
    assert msg_texts[-1]["chat_id"] == 777
    assert msg_texts[-1]["text"]


# --------------------------------------------------------------------------- #
# UNAUTHORIZED sender => spawns NOTHING; polite deny (no tools / no media).
# --------------------------------------------------------------------------- #
async def test_unauthorized_sender_spawns_nothing(platform):
    fake = FakeTelegram([_update(10, sender=999, text="rm -rf /")])
    ch = _telegram(
        fake,
        {"token_secret": "tg_token", "inbound_enabled": True, "allowed_senders": [777]},
    )
    poller, orch = _poller(platform, ch)

    results = await poller.poll_once()

    assert results[0]["status"] == "unauthorized"
    assert results[0]["sender"] == "999"
    assert orch.list_sessions() == []
    # Denial reply only — never a session / never generation.
    msg_texts = [s for s in fake.sent if s.get("text")]
    assert len(msg_texts) == 1
    assert "permission" in (msg_texts[0].get("text") or "").lower()
    assert "999" in (msg_texts[0].get("text") or "")


async def test_empty_allowlist_authorizes_nobody(platform):
    """Fail-closed: an empty/missing allowlist rejects every sender."""
    fake = FakeTelegram([_update(10, sender=777, text="hello")])
    ch = _telegram(
        fake, {"token_secret": "tg_token", "inbound_enabled": True}  # no allowed_senders
    )
    poller, orch = _poller(platform, ch)

    results = await poller.poll_once()

    assert results[0]["status"] == "unauthorized"
    assert orch.list_sessions() == []
    # Still tells the stranger the bot is gated (no tools run).
    assert any("private" in (s.get("text") or "").lower() or "permission" in (s.get("text") or "").lower()
               for s in fake.sent if s.get("text"))


async def test_bot_messages_are_ignored(platform):
    """Loop protection: the bot's own / other bots' messages never act."""
    fake = FakeTelegram([_update(10, sender=777, text="echo", is_bot=True)])
    ch = _telegram(
        fake,
        {"token_secret": "tg_token", "inbound_enabled": True, "allowed_senders": [777]},
    )
    poller, orch = _poller(platform, ch)

    results = await poller.poll_once()

    assert results[0]["status"] == "ignored_bot"
    assert orch.list_sessions() == []


# --------------------------------------------------------------------------- #
# DURABLE OFFSET — advances + dedupes across a restart (fresh poller/orch).
# --------------------------------------------------------------------------- #
async def test_offset_advances_and_dedupes_on_restart(platform):
    fake = FakeTelegram([_update(42, sender=777, text="task one")])
    cfg = {"token_secret": "tg_token", "inbound_enabled": True, "allowed_senders": [777]}

    # First boot: process the one message.
    poller1, orch1 = _poller(platform, _telegram(fake, cfg))
    await poller1.poll_once()
    assert len(orch1.list_sessions()) == 1

    # The durable offset advanced to update_id + 1.
    with session_scope(platform.engine) as db:
        rec = db.get(InboundOffsetRecord, "tg")
    assert rec is not None and rec.offset == 43

    # Simulate a restart: a brand-new poller + orchestrator over the SAME engine
    # and the SAME transport (still holding update 42). It must NOT reprocess.
    # (Both orchestrators share the DB, so the count must STAY at 1, not grow.)
    poller2, orch2 = _poller(platform, _telegram(fake, cfg))
    results = await poller2.poll_once()
    assert results == []  # offset-confirmed => getUpdates returns nothing new
    assert len(orch2.list_sessions()) == 1  # no duplicate session spawned


async def test_offset_persists_across_multiple_messages(platform):
    fake = FakeTelegram(
        [
            _update(1, sender=777, text="first"),
            _update(2, sender=777, text="second"),
        ]
    )
    cfg = {"token_secret": "tg_token", "inbound_enabled": True, "allowed_senders": [777]}
    poller, orch = _poller(platform, _telegram(fake, cfg))

    await poller.poll_once()

    assert len(orch.list_sessions()) == 2
    with session_scope(platform.engine) as db:
        rec = db.get(InboundOffsetRecord, "tg")
    assert rec.offset == 3


# --------------------------------------------------------------------------- #
# build_notifier plumbs the two-way config onto the channel.
# --------------------------------------------------------------------------- #
def test_build_notifier_preserves_inbound_config():
    fake = FakeTelegram([])
    cfg = {
        "channels": {
            "tg": {
                "type": "telegram",
                "token_secret": "tg_token",
                "inbound_enabled": True,
                "allowed_senders": [777, "888"],
            }
        }
    }
    notifier = build_notifier(
        cfg,
        secret_resolver=lambda n: "TOK",
        http_post=fake.post,
        http_get=fake.get,
    )
    ch = notifier.get("tg")
    assert ch.inbound_enabled() is True
    assert ch.allowed_senders() == {"777", "888"}
    assert ch.is_authorized(777) is True  # int id matches stringified allowlist
    assert ch.is_authorized(123) is False


def test_non_inbound_channel_types_never_poll():
    """Outbound-only channels report no inbound leg and yield nothing on poll.

    Slack moved OUT of this set in v1.16: it is inbound-capable via SOCKET MODE
    (an outbound WebSocket — see comm/slack_socket.py), though its HTTP poll
    leg stays a no-op (the socket, not the poller, delivers its messages).
    """
    from iron_jarvis.comm import DiscordChannel, SlackChannel

    ch = DiscordChannel({"webhook_url": "u", "inbound_enabled": True, "allowed_senders": [1]})
    assert ch.supports_inbound is False
    assert ch.inbound_enabled() is False  # type can't receive, so stays off
    assert ch.poll(0) == ([], 0)

    slack = SlackChannel(
        {"webhook_url": "u", "inbound_enabled": True, "allowed_senders": ["U1"]}
    )
    assert slack.supports_inbound is True  # Socket Mode receive leg
    assert slack.poll(0) == ([], 0)  # but polling delivers nothing — the socket does


async def test_group_chat_message_is_refused(platform):
    # chat.id != sender id => a group/non-private chat. Even from an allowlisted
    # sender it must NOT run, since replying would broadcast output to the group.
    upd = {
        "update_id": 11,
        "message": {"text": "do it", "from": {"id": 777, "is_bot": False}, "chat": {"id": -100999}},
    }
    fake = FakeTelegram([upd])
    ch = _telegram(
        fake,
        {"token_secret": "tg_token", "inbound_enabled": True, "allowed_senders": [777]},
    )
    poller, orch = _poller(platform, ch)
    results = await poller.poll_once()
    assert results[0]["status"] == "non_private"
    assert orch.list_sessions() == []  # nothing ran
    assert fake.sent == []  # nothing broadcast


# --------------------------------------------------------------------------- #
# MEDIA INTENT — Telegram must generate + attach media when asked.
# --------------------------------------------------------------------------- #
def test_detect_media_intent_phrases():
    d = InboundPoller._detect_media_intent
    assert d("generate an image of a red fox") is True
    assert d("Create a picture of the moon") is True
    assert d("make me a logo for my brand") is True
    assert d("draw a poster of a city") is True
    assert d("text-to-image a cyberpunk street") is True
    assert d("generate a video of waves") is True
    assert d("compose a song about rain") is True
    assert d("image of a cat") is True
    # Non-media chat must stay false (no forced Pixio spend).
    assert d("do the thing") is False
    assert d("what time is it") is False
    assert d("summarize this document") is False
    assert d("") is False


def test_media_kind_and_prompt_helpers():
    assert InboundPoller._media_kind("generate a video of rain") == "video"
    assert InboundPoller._media_kind("make a song about hope") == "audio"
    assert InboundPoller._media_kind("draw a picture of a fox") == "image"
    prompt = InboundPoller._media_prompt("generate an image of a red fox in neon")
    assert "red fox" in prompt.lower()
    assert "generate" not in prompt.lower()


def test_pick_pixio_model_prefers_matching_kind():
    models = [
        {"id": "pixio/flux", "name": "Flux", "type": "image"},
        {"id": "pixio/veo", "name": "Veo", "type": "video"},
        {"id": "pixio/suno", "name": "Suno", "type": "audio"},
    ]
    assert InboundPoller._pick_pixio_model(models, kind="video") == "pixio/veo"
    assert InboundPoller._pick_pixio_model(models, kind="audio") == "pixio/suno"
    assert InboundPoller._pick_pixio_model(models, kind="image") == "pixio/flux"
    assert InboundPoller._pick_pixio_model([], kind="image") == ""


def test_collect_session_media_finds_pixio_outputs(tmp_path):
    pix = tmp_path / "pixio"
    pix.mkdir()
    (pix / "gen.png").write_bytes(b"\x89PNG\r\n" + b"0" * 64)
    (tmp_path / "notes.txt").write_text("not media")
    found = InboundPoller._collect_session_media(str(tmp_path))
    assert len(found) == 1 and found[0].name == "gen.png"


async def test_media_request_uses_media_ack_and_fallback_when_no_files(platform, tmp_path, monkeypatch):
    """When the user asks for media and the agent leaves no files, fallback runs.

    We stub Pixio so the fallback writes a PNG into the session workspace and
    Telegram send_media is recorded via a channel method override.
    """
    fake = FakeTelegram([_update(50, sender=777, text="generate an image of a blue robot")])
    ch = _telegram(
        fake,
        {"token_secret": "tg_token", "inbound_enabled": True, "allowed_senders": [777]},
    )
    media_sent: list[str] = []

    def _send_media(path, *, chat_id=None, caption="", kind=None):
        media_sent.append(str(path))
        return {"ok": True, "detail": "fake-media", "path": str(path)}

    ch.send_media = _send_media  # type: ignore[method-assign]

    poller, orch = _poller(platform, ch)

    async def _fake_ensure(user_text, workspace, *, session_id="", reference_images=None):
        root = Path(workspace)
        root.mkdir(parents=True, exist_ok=True)
        out = root / "pixio" / "fallback.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"\x89PNG\r\n" + b"x" * 32)
        return {"ok": True, "model_id": "pixio/flux", "saved_path": "pixio/fallback.png"}

    monkeypatch.setattr(poller, "_ensure_media_generated", _fake_ensure)

    results = await poller.poll_once()

    assert results[0]["status"] == "handled"
    assert results[0].get("media_intent") is True
    assert results[0].get("media_fallback") is True
    assert results[0].get("media_sent", 0) >= 1
    assert media_sent, "send_media should have been called with the generated file"
    msg_texts = [s.get("text") or "" for s in fake.sent if s.get("text")]
    assert any("Generating that media" in t for t in msg_texts)


async def test_non_media_message_does_not_force_fallback(platform, monkeypatch):
    fake = FakeTelegram([_update(51, sender=777, text="what is 2+2")])
    ch = _telegram(
        fake,
        {"token_secret": "tg_token", "inbound_enabled": True, "allowed_senders": [777]},
    )
    poller, orch = _poller(platform, ch)

    called = {"n": 0}

    async def _should_not_run(*_a, **_k):
        called["n"] += 1
        return {"ok": False, "error": "should not run"}

    monkeypatch.setattr(poller, "_ensure_media_generated", _should_not_run)
    results = await poller.poll_once()
    assert results[0]["status"] == "handled"
    assert results[0].get("media_intent") is False
    assert called["n"] == 0


# --------------------------------------------------------------------------- #
# PHOTO UPLOAD → image-to-video
# --------------------------------------------------------------------------- #
def _photo_update(update_id: int, sender: int, *, caption: str = "", file_id: str = "FILE1") -> dict:
    msg: dict[str, Any] = {
        "from": {"id": sender, "is_bot": False},
        "chat": {"id": sender},
        "photo": [
            {"file_id": "small", "file_unique_id": "u1", "width": 90, "height": 90, "file_size": 100},
            {"file_id": file_id, "file_unique_id": "u2", "width": 800, "height": 600, "file_size": 5000},
        ],
    }
    if caption:
        msg["caption"] = caption
    return {"update_id": update_id, "message": msg}


def test_telegram_poll_accepts_photo_with_caption():
    fake = FakeTelegram([_photo_update(70, 777, caption="make a video of this")])
    ch = _telegram(
        fake,
        {"token_secret": "tg_token", "inbound_enabled": True, "allowed_senders": [777]},
    )
    messages, next_offset = ch.poll(0)
    assert next_offset == 71
    assert len(messages) == 1
    m = messages[0]
    assert m.text == "make a video of this"
    assert len(m.attachments) == 1
    assert m.attachments[0].file_id == "FILE1"
    assert m.attachments[0].kind == "photo"


def test_telegram_poll_accepts_photo_only_without_caption():
    fake = FakeTelegram([_photo_update(71, 777, caption="")])
    ch = _telegram(
        fake,
        {"token_secret": "tg_token", "inbound_enabled": True, "allowed_senders": [777]},
    )
    messages, _ = ch.poll(0)
    assert len(messages) == 1
    assert messages[0].text == ""
    assert messages[0].attachments[0].file_id == "FILE1"


def test_media_kind_defaults_to_video_with_reference_photo():
    assert InboundPoller._media_kind("make a video", has_reference_image=True) == "video"
    assert InboundPoller._media_kind("animate this", has_reference_image=True) == "video"
    assert InboundPoller._media_kind("hello", has_reference_image=True) == "video"
    assert InboundPoller._media_kind("generate an image of a cat", has_reference_image=False) == "image"


def test_collect_session_media_excludes_inbound_uploads(tmp_path):
    inbound = tmp_path / "inbound"
    inbound.mkdir()
    (inbound / "photo.jpg").write_bytes(b"\xff\xd8\xff" + b"0" * 32)
    pix = tmp_path / "pixio"
    pix.mkdir()
    (pix / "out.mp4").write_bytes(b"ftyp" + b"0" * 64)
    found = InboundPoller._collect_session_media(
        str(tmp_path), exclude_paths={str(inbound / "photo.jpg")}
    )
    assert len(found) == 1 and found[0].name == "out.mp4"


async def test_photo_upload_triggers_video_pipeline(platform, monkeypatch):
    """Photo + caption 'make a video' downloads the still, runs i2v fallback, attaches video."""
    fake = FakeTelegram([_photo_update(80, 777, caption="make a video of this moving")])
    ch = _telegram(
        fake,
        {"token_secret": "tg_token", "inbound_enabled": True, "allowed_senders": [777]},
    )
    media_sent: list[str] = []

    def _send_media(path, *, chat_id=None, caption="", kind=None):
        media_sent.append(str(path))
        return {"ok": True, "detail": "fake", "path": str(path)}

    ch.send_media = _send_media  # type: ignore[method-assign]

    def _download(att, dest):
        p = Path(dest)
        if p.is_dir():
            p = p / "photo.jpg"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"\xff\xd8\xff" + b"JPG" * 20)
        return {"ok": True, "path": str(p), "detail": "saved", "bytes": p.stat().st_size}

    ch.download_attachment = _download  # type: ignore[method-assign]

    poller, orch = _poller(platform, ch)

    async def _fake_ensure(user_text, workspace, *, session_id="", reference_images=None):
        assert reference_images, "reference photo must be downloaded for i2v"
        root = Path(workspace)
        out = root / "pixio" / "out.mp4"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"ftypisom" + b"0" * 64)
        return {"ok": True, "model_id": "pixio/veo", "kind": "video", "saved_path": "pixio/out.mp4"}

    monkeypatch.setattr(poller, "_ensure_media_generated", _fake_ensure)

    results = await poller.poll_once()
    assert results[0]["status"] == "handled"
    assert results[0].get("media_intent") is True
    assert results[0].get("media_fallback") is True
    assert results[0].get("media_sent", 0) >= 1
    assert any(p.endswith(".mp4") for p in media_sent)
    texts = [s.get("text") or "" for s in fake.sent if s.get("text")]
    assert any("photo" in t.lower() and "video" in t.lower() for t in texts)
