"""Two-way comm: the durable inbound poller (remote command surface).

The notifier's channels only PUSH out. :class:`InboundPoller` adds the receive
leg: it long-polls every channel whose inbound is *explicitly* enabled, and for
each AUTHORIZED message spawns a normal supervised session via the orchestrator,
awaits it, and replies the summary back over the same channel.

SECURITY (this drives the machine from a phone, so it is hardened by design):

* OFF BY DEFAULT / OPT-IN — :meth:`enabled` is True only when at least one
  channel has ``inbound_enabled = true`` *and* its credentials resolve. With no
  channels configured (the default + the test suite) the daemon never creates
  the loop: zero polling, zero network.
* SENDER ALLOWLIST, FAIL-CLOSED — a message is processed only when
  ``channel.is_authorized(sender_id)`` (an empty/missing allowlist authorizes
  nobody). An unauthorized sender NEVER spawns a session.
* NORMAL GATES — sessions run through the same orchestrator + permission engine
  as a local user, so a remote sender gets no extra power (dangerous tools still
  fail-closed under the headless ask-resolver).
* LOOP PROTECTION — the bot's own / other bots' messages are ignored.
* DURABLE OFFSET — the last-seen offset is persisted per channel so a restart
  resumes without reprocessing.

Mirrors the daemon's auto-backup / autonomy loops: the loop body sleeps, never
blocks boot, and is cancelled on shutdown.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any

from sqlalchemy import Engine

from ..core.db import session_scope
from ..core.events import EventType
from ..core.ids import utcnow
from ..core.logging import get_logger
from ..core.models import AgentType
from .base import Channel, InboundMessage
from .models import InboundOffsetRecord

log = get_logger("comm.inbound")

#: Media extensions the Telegram bot will auto-attach after a free-text session.
_MEDIA_EXTS = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".webp",
    ".mp4", ".webm", ".mov",
    ".mp3", ".wav", ".ogg", ".m4a",
})
#: Cap how many files we push per reply (Telegram UX + rate limits).
_MAX_MEDIA_PER_REPLY = 6

#: User phrasing that means "generate media" (Telegram free-text path).
#: Matched case-insensitively; keep high-precision so chatty messages don't
#: force a Pixio spend.
_MEDIA_INTENT_RX = re.compile(
    r"(?is)\b("
    r"generate|generat(?:e|ing|ed)|create|make|draw|render|paint|design|"
    r"produce|compose|synthesize|imagine|illustrate"
    r")\b.{0,80}\b("
    r"image|images|picture|pictures|photo|photos|pic|pics|art|artwork|"
    r"illustration|logo|icon|poster|thumbnail|wallpaper|avatar|"
    r"video|videos|clip|clips|animation|animations|gif|gifs|"
    r"audio|song|songs|music|track|sound|sounds|voiceover|"
    r"media|visual|visuals"
    r")\b"
    r"|"
    r"\b("
    r"image|picture|photo|pic|art|logo|video|clip|song|music|audio|media"
    r")\s+of\b"
    r"|"
    r"\b(text[- ]to[- ]image|text[- ]to[- ]video|text[- ]to[- ]audio|txt2img)\b"
)

_IMAGE_KIND_RX = re.compile(
    r"(?is)\b(image|images|picture|pictures|photo|photos|pic|pics|art|artwork|"
    r"illustration|logo|icon|poster|thumbnail|wallpaper|avatar|visual|visuals)\b"
)
_VIDEO_KIND_RX = re.compile(
    r"(?is)\b(video|videos|clip|clips|animation|animations|gif|gifs|cinematic)\b"
)
_AUDIO_KIND_RX = re.compile(
    r"(?is)\b(audio|song|songs|music|track|sound|sounds|voiceover|soundtrack)\b"
)

#: Public-facing denial when someone finds the bot (e.g. via X) without allowlist.
_UNAUTHORIZED_REPLY = (
    "Epic Tech AI is private and gated.\n"
    "You need the owner's explicit permission before any chat, tools, or "
    "media generation can run.\n\n"
    "Request access: epictechai@gmail.com · X @EpicTechAI\n"
    "Your Telegram user id is shown below — the owner must add it to the "
    "allowlist before anything works.\n"
    "Your id: {sender_id}"
)

#: Soft rate-limit for unauthorized denials (seconds per sender) so a public
#: bot post on X cannot be used to spam Telegram replies.
_UNAUTHORIZED_REPLY_COOLDOWN_S = 120.0


class InboundPoller:
    """Polls inbound-enabled channels and runs supervised sessions for replies."""

    def __init__(
        self,
        notifier: Any,
        orchestrator: Any,
        engine: Engine,
        *,
        event_bus: Any = None,
        poll_timeout: int = 0,
        # BUILDER answers free-text chat directly; SUPERVISOR only "delegates"
        # and produces useless Telegram summaries under headless permissions.
        agent_type: AgentType = AgentType.BUILDER,
        reply_prefix: str = "Epic Tech AI: ",
        max_reply_chars: int = 3500,
        command_interpreter: Any = None,
        reflex_router: Any = None,
    ) -> None:
        self.notifier = notifier
        self.orchestrator = orchestrator
        self.engine = engine
        self.event_bus = event_bus
        self.poll_timeout = poll_timeout
        self.agent_type = agent_type
        self.reply_prefix = reply_prefix
        self.max_reply_chars = max_reply_chars
        #: The Reflex command grammar (``/status``, ``/run`` …). When set, an
        #: authorized message that starts with ``/`` is handled as a fast,
        #: deterministic command instead of spawning a full agent session.
        self.command_interpreter = command_interpreter
        #: The Reflex router. When set, an authorized NON-command message that
        #: matches a ``comm`` reflex rule (keyword) fires that rule instead of a
        #: free-form session — so "any message mentioning X → run workflow Y".
        self.reflex_router = reflex_router
        #: sender_id -> monotonic last unauthorized reply time (process-local).
        self._unauth_reply_at: dict[str, float] = {}

    # -- discovery ---------------------------------------------------------
    def inbound_channels(self) -> list[tuple[str, Channel]]:
        """``(name, channel)`` for every channel that is opted-in AND credentialed.

        Uses the notifier's public API only. A channel toggled on but missing
        its token is skipped (so it is not polled with no credentials).
        """
        out: list[tuple[str, Channel]] = []
        for name in self.notifier.channels():
            ch = self.notifier.get(name)
            if ch is None or not ch.inbound_enabled():
                continue
            if not ch.has_credentials():
                continue
            out.append((name, ch))
        return out

    def enabled(self) -> bool:
        """True iff any channel is configured for inbound (guards loop creation)."""
        return bool(self.inbound_channels())

    # -- durable offset ----------------------------------------------------
    def _get_offset(self, channel: str) -> int:
        with session_scope(self.engine) as db:
            rec = db.get(InboundOffsetRecord, channel)
            return rec.offset if rec is not None else 0

    def _set_offset(self, channel: str, offset: int) -> None:
        with session_scope(self.engine) as db:
            rec = db.get(InboundOffsetRecord, channel)
            if rec is None:
                rec = InboundOffsetRecord(channel=channel, offset=offset)
            else:
                rec.offset = offset
            rec.updated_at = utcnow()
            db.merge(rec)
            db.commit()

    # -- one polling pass --------------------------------------------------
    async def poll_once(self) -> list[dict[str, Any]]:
        """Poll every inbound channel once and handle each message.

        Returns a per-message result list (for tests/observability). Never
        raises: a single bad channel/message is logged and skipped.
        """
        results: list[dict[str, Any]] = []
        for name, ch in self.inbound_channels():
            offset = self._get_offset(name)
            try:
                # The poll is blocking HTTP — run it off the event loop so a
                # long-poll never stalls the daemon. ``to_thread`` of a synchronous
                # (test) transport is still deterministic.
                messages, next_offset = await asyncio.to_thread(
                    ch.poll, offset, timeout=self.poll_timeout
                )
            except Exception:  # noqa: BLE001 — never let one channel kill the pass
                log.exception("inbound poll failed for channel %r", name)
                continue
            for msg in messages:
                # AT-MOST-ONCE on a remote COMMAND surface: persist the offset
                # BEFORE running, so a crash mid-handling drops the in-flight
                # message rather than re-running a remote-triggered action on
                # restart (duplicate side effects are worse than a dropped reply).
                if isinstance(msg.update_id, int):
                    offset = max(offset, msg.update_id + 1)
                    self._set_offset(name, offset)
                try:
                    res = await self._handle(name, ch, msg)
                except Exception as exc:  # noqa: BLE001 — keep processing the batch
                    log.exception("inbound handling failed on channel %r", name)
                    # Always tell the user something went wrong (don't fail silent).
                    try:
                        err_body = (
                            f"{self.reply_prefix}Sorry — I hit an error "
                            f"({type(exc).__name__}). Try again in a moment."
                        )[: self.max_reply_chars]
                        await asyncio.to_thread(
                            ch.send, err_body, chat_id=msg.reply_to
                        )
                    except Exception:  # noqa: BLE001
                        log.exception("inbound error reply failed")
                    res = {"channel": name, "status": "error", "error": type(exc).__name__}
                results.append(res)
            # Some channels report a high-water offset even with no text messages
            # (e.g. only non-text updates); persist it so we don't refetch them.
            if next_offset > offset:
                self._set_offset(name, next_offset)
        return results

    async def _handle(
        self, name: str, ch: Channel, msg: InboundMessage
    ) -> dict[str, Any]:
        """Authorize, then (if allowed) run a supervised session + reply."""
        # Loop protection: never act on a bot's message (incl. our own echoes).
        if msg.is_bot:
            return {"channel": name, "status": "ignored_bot"}

        # FAIL-CLOSED allowlist. An unauthorized sender NEVER runs commands,
        # sessions, tools, or media generation — owner permission only.
        if not ch.is_authorized(msg.sender_id):
            log.warning(
                "inbound: rejected unauthorized sender %r on channel %r",
                msg.sender_id,
                name,
            )
            await self._publish(
                EventType.COMM_REJECTED,
                {"channel": name, "sender": msg.sender_id},
            )
            replied = await self._reply_unauthorized(ch, msg)
            return {
                "channel": name,
                "status": "unauthorized",
                "sender": str(msg.sender_id),
                "replied": replied,
            }

        # PRIVATE-CHAT ONLY: in a group the originating chat.id != the sender's id,
        # and replying there would broadcast the session output to non-allowlisted
        # members. Refuse anything that isn't the sender's own 1:1 chat.
        if msg.reply_to is not None and str(msg.reply_to) != str(msg.sender_id):
            log.warning("inbound: refusing non-private chat on channel %r", name)
            # Never post into the group (would leak to non-allowlisted members).
            # Quiet refuse only — no session, no media, no group broadcast.
            return {"channel": name, "status": "non_private", "sender": str(msg.sender_id)}

        text = (msg.text or "").strip()
        attachments = list(getattr(msg, "attachments", None) or [])
        if not text and not attachments:
            return {"channel": name, "status": "empty"}
        # Photo-only uploads still need an instruction; default to image-to-video
        # when a still is attached with no caption so the bot doesn't no-op.
        if not text and attachments:
            text = "Animate this uploaded image into a short video."

        # COMMAND GRAMMAR: an authorized "/command" is a fast, deterministic
        # operation (status / run a workflow / cancel / ask a remote agent),
        # replied immediately — no agent session spun up. Non-command text falls
        # through to the normal session path below. (Commands never carry media.)
        if self.command_interpreter is not None and text.startswith("/") and not attachments:
            await asyncio.to_thread(ch.typing, msg.reply_to)
            reply = await self.command_interpreter.interpret(text)
            if reply is not None:
                body = self._format_reply(reply)
                send_res = await asyncio.to_thread(ch.send, body, chat_id=msg.reply_to)
                await self._publish(
                    EventType.COMM_RECEIVED,
                    {"channel": name, "sender": msg.sender_id, "command": text},
                )
                return {
                    "channel": name,
                    "status": "command",
                    "command": text.split()[0].split("@", 1)[0],
                    "sent": bool(send_res.get("ok")),
                    "detail": send_res.get("detail"),
                }

        # REFLEX (comm): a non-command message that matches a keyword rule fires
        # that rule (run a workflow / remote agent / session) instead of a
        # free-form chat — the ambient-operator path for "mention X → do Y".
        if self.reflex_router is not None:
            try:
                fired = await self.reflex_router.on_comm(text)
            except Exception:  # noqa: BLE001 — a reflex must never break comm
                fired = []
            fired = [f for f in fired if f.get("ok")]
            if fired:
                summary = "; ".join(
                    f"{f.get('kind', 'action')} {f.get('rule', '')}".strip() for f in fired
                )
                body = f"{self.reply_prefix}Triggered: {summary}"[: self.max_reply_chars]
                send_res = await asyncio.to_thread(ch.send, body, chat_id=msg.reply_to)
                return {
                    "channel": name,
                    "status": "reflex",
                    "fired": len(fired),
                    "sent": bool(send_res.get("ok")),
                }

        # Live chat UX: typing indicator + short "working" ack, then run the
        # session while refreshing typing so Telegram shows activity.
        chat_id = msg.reply_to
        # Photo upload and/or explicit generate language → media pipeline.
        media_intent = self._detect_media_intent(text) or bool(attachments)
        await asyncio.to_thread(ch.typing, chat_id)
        if attachments:
            kind_hint = self._media_kind(text, has_reference_image=True)
            ack = (
                "Got your photo — generating the video…"
                if kind_hint == "video"
                else "Got your photo — generating media…"
            )
        elif media_intent:
            ack = "Generating that media for you…"
        else:
            ack = "Working on it…"
        await asyncio.to_thread(
            ch.send, self._format_reply(ack), chat_id=chat_id
        )

        # Full-capability free-text: BUILDER + lead model with tools —
        # code, memory, docs, web, and Pixio media generation. Media files left in
        # the session workspace are attached on the reply after the summary.
        # When the user clearly asked for media, the task is hard-required to
        # call pixio_* AND we fall back to a direct Pixio generation if the
        # agent finishes without leaving files (so Telegram always gets media).
        # Uploaded photos are downloaded into the session workspace first and
        # used as image-to-video reference frames when a video is requested.
        cfg = getattr(getattr(self.orchestrator, "p", None), "config", None)
        provider = getattr(cfg, "default_provider", None) if cfg else None
        model = getattr(cfg, "default_model", None) if cfg else None

        # Create the session first so we have a workspace for inbound downloads.
        task_placeholder = self._build_session_task(
            text, media_intent=media_intent, reference_images=[]
        )
        session = await self.orchestrator.create_session(
            task_placeholder,
            self.agent_type,
            provider=provider,
            model=model,
            origin="comm",
        )
        workspace = getattr(session, "workspace_path", "") or ""
        reference_images = await self._download_inbound_attachments(
            ch, attachments, workspace
        )
        # Rebuild the task with concrete local paths once downloads finish so
        # the agent sees image-to-video instructions + workspace paths.
        if reference_images:
            task = self._build_session_task(
                text, media_intent=True, reference_images=reference_images
            )
            try:
                session.task = task
                save = getattr(self.orchestrator, "_save", None)
                if callable(save):
                    save(session)
            except Exception:  # noqa: BLE001 — task update is best-effort
                log.exception("failed to persist media task with reference images")

        # Suppress the generic session.completed push-alert — we reply in-chat.
        notifier = getattr(self, "notifier", None)
        if notifier is not None and hasattr(notifier, "suppress_session_alert"):
            notifier.suppress_session_alert(session.id)
        await self._publish(
            EventType.COMM_RECEIVED,
            {
                "channel": name,
                "sender": msg.sender_id,
                "task": text,
                "media_intent": bool(media_intent),
                "attachments": len(attachments),
                "reference_images": len(reference_images),
            },
            session_id=session.id,
        )

        run_task = asyncio.create_task(self.orchestrator.run_session(session.id))
        # Refresh typing every ~4s while the agent works (Telegram TTL ~5s).
        while not run_task.done():
            await asyncio.to_thread(ch.typing, chat_id)
            try:
                await asyncio.wait_for(asyncio.shield(run_task), timeout=4.0)
            except asyncio.TimeoutError:
                continue
        session = await run_task

        workspace = getattr(session, "workspace_path", "") or workspace
        # Exclude the user's uploaded reference stills from "generated" media —
        # only newly produced outputs under pixio/ (or non-inbound paths) attach.
        media_paths = self._collect_session_media(
            workspace, exclude_paths=set(reference_images)
        )
        media_fallback = False
        media_error = ""

        # Guarantee: if the user asked for media and the agent produced none,
        # generate directly via Pixio (image-to-video when a photo was uploaded).
        if media_intent and not media_paths:
            await asyncio.to_thread(ch.typing, chat_id)
            try:
                fb = await self._ensure_media_generated(
                    text,
                    workspace,
                    session_id=getattr(session, "id", "") or "",
                    reference_images=reference_images,
                )
                media_fallback = bool(fb.get("ok"))
                media_error = str(fb.get("error") or "")
                media_paths = self._collect_session_media(
                    workspace, exclude_paths=set(reference_images)
                )
            except Exception as exc:  # noqa: BLE001 — never kill the text reply
                log.exception("telegram media fallback failed")
                media_error = f"{type(exc).__name__}: {exc}"

        reply = (session.summary or "").strip() or "(no result)"
        # Prefer a clean chat answer over a raw system dump / failed delegate.
        if reply.startswith("Delegated the task") or "all subtasks complete" in reply:
            reply = (
                "I'm Epic Tech AI — your local AI OS assistant. "
                "I can run tasks, workflows, tools, and generate media on this machine. "
                "Ask me anything, or try /help for commands."
            )
        if media_intent and media_paths:
            if media_fallback:
                reply = (
                    f"Generated {len(media_paths)} media file(s) and attached "
                    f"{'them' if len(media_paths) != 1 else 'it'} below."
                )
            elif not any(
                token in reply.lower()
                for token in ("generated", "image", "video", "audio", "media", "pixio")
            ):
                reply = (
                    f"{reply.rstrip()}\n\n"
                    f"Attached {len(media_paths)} generated media file(s)."
                ).strip()
        elif media_intent and not media_paths:
            # Be honest when generation could not run (missing key / API error).
            hint = media_error or (
                "Pixio is not configured — add a secret named 'pixio' "
                "(Connections / Secrets) or set PIXIO_API_KEY."
            )
            reply = (
                f"{reply.rstrip()}\n\n"
                f"Could not generate media: {hint}"
            ).strip()

        body = self._format_reply(reply)
        # Safe to reply to the originating chat: we only reach here for the
        # sender's own private chat (the non-private guard above refused groups).
        send_res = await asyncio.to_thread(ch.send, body, chat_id=chat_id)
        media_sent = 0
        send_media = getattr(ch, "send_media", None)
        if callable(send_media) and media_paths:
            await asyncio.to_thread(ch.typing, chat_id)
            for i, mpath in enumerate(media_paths):
                cap = mpath.name if i == 0 else ""
                try:
                    mres = await asyncio.to_thread(
                        send_media, mpath, chat_id=chat_id, caption=cap
                    )
                    if mres and mres.get("ok"):
                        media_sent += 1
                except Exception:  # noqa: BLE001 — media must not kill the text reply
                    log.exception("failed to send media %s", mpath)
        return {
            "channel": name,
            "status": "handled",
            "session_id": session.id,
            "sent": bool(send_res.get("ok")),
            "detail": send_res.get("detail"),
            "media_intent": bool(media_intent),
            "media_fallback": media_fallback,
            "media_sent": media_sent,
            **({"media_error": media_error} if media_error else {}),
        }

    @staticmethod
    def _detect_media_intent(text: str) -> bool:
        """True when the user is clearly asking to generate image/video/audio."""
        t = (text or "").strip()
        if not t:
            return False
        return bool(_MEDIA_INTENT_RX.search(t))

    @staticmethod
    def _media_kind(text: str, *, has_reference_image: bool = False) -> str:
        """Best-effort media kind for model selection: image | video | audio.

        When a photo was uploaded, default to **video** (image-to-video) unless
        the user explicitly asked for audio only.
        """
        t = text or ""
        if re.search(
            r"(?is)\b(audio|song|songs|music|track|sound|sounds|voiceover|soundtrack)\b",
            t,
        ) and not re.search(r"(?is)\b(video|clip|animate)\b", t):
            return "audio"
        if re.search(
            r"(?is)\b(video|videos|clip|clips|animation|animations|gif|gifs|"
            r"animate|motion|i2v|img2vid|bring\s+to\s+life)\b",
            t,
        ):
            return "video"
        if has_reference_image:
            # Uploaded still + "generate" / default caption → animate to video.
            return "video"
        return "image"

    def _build_session_task(
        self,
        text: str,
        *,
        media_intent: bool,
        reference_images: list[str] | None = None,
    ) -> str:
        """Build the BUILDER task for a Telegram free-text / photo message."""
        refs = [p for p in (reference_images or []) if p]
        has_ref = bool(refs)
        base = (
            "You are Epic Tech AI — the user's local AI operating system on this "
            "machine (brand: Epic Tech AI · epictechai@gmail.com · X @EpicTechAI). "
            "You are NOT Iron Jarvis.\n"
            "Channel: Telegram. Reply in clear, concise plain text suitable for mobile.\n"
            "FULL CAPABILITY — use tools when they help:\n"
            "- Talk, plan, code, edit files in the workspace, search memory/LTM\n"
            "- Read/write documents; create workflows/schedules when asked\n"
            "- Web search when facts need a live lookup\n"
            "- MEDIA: when the user wants an image, video, audio, or visual, use "
            "pixio_models → pixio_params → pixio_generate (pixio_status if needed). "
            "Save outputs under pixio/ in the workspace; the system will attach "
            "those files to Telegram automatically.\n"
            "Do not invent tool results. If you only need to talk, just talk.\n"
            "Finish with a short plain-language summary of what you did.\n\n"
        )
        if media_intent or has_ref:
            kind = self._media_kind(text, has_reference_image=has_ref)
            base += (
                "MEDIA REQUEST — REQUIRED:\n"
                f"The user asked you to GENERATE {kind} media. You MUST call "
                "pixio_models, then pixio_params for the chosen model, then "
                "pixio_generate with wait=true and a clear prompt derived from "
                "their message. Do NOT only describe the media — actually generate "
                "it. Leave the file under pixio/ in the workspace.\n"
            )
            if has_ref and kind == "video":
                paths = ", ".join(refs)
                base += (
                    "IMAGE-TO-VIDEO — the user UPLOADED a reference photo. "
                    "You MUST use it as the source frame:\n"
                    f"  Local file(s): {paths}\n"
                    "1) Call pixio_upload with path=<that file> to get a permanent "
                    "public URL (or use the path if the model accepts local refs).\n"
                    "2) Call pixio_params on an image-to-video / video model and pass "
                    "the uploaded image URL into the param the schema lists "
                    "(often image / image_url / init_image / first_frame / url).\n"
                    "3) pixio_generate with wait=true; leave the VIDEO under pixio/.\n"
                    "Do NOT ignore the uploaded photo. Do NOT only generate a new still.\n"
                )
            base += (
                "If Pixio is unavailable, say so plainly in the summary.\n\n"
            )
        if refs:
            base += "Uploaded reference files (workspace paths):\n"
            for p in refs:
                base += f"- {p}\n"
            base += "\n"
        return base + f"User message:\n{text}"

    async def _download_inbound_attachments(
        self, ch: Channel, attachments: list[Any], workspace: str
    ) -> list[str]:
        """Download Telegram photos into ``workspace/inbound/``; return local paths."""
        if not attachments:
            return []
        download = getattr(ch, "download_attachment", None)
        if not callable(download):
            log.warning("channel %s cannot download attachments", getattr(ch, "name", "?"))
            return []
        root = Path(workspace or "")
        if not root.is_dir():
            try:
                root.mkdir(parents=True, exist_ok=True)
            except OSError:
                return []
        inbound_dir = root / "inbound"
        inbound_dir.mkdir(parents=True, exist_ok=True)
        saved: list[str] = []
        for i, att in enumerate(attachments):
            # Prefer photo/document images only for image-to-video refs.
            kind = getattr(att, "kind", None) or (
                att.get("kind") if isinstance(att, dict) else ""
            )
            if str(kind) not in ("photo", "document", "image", ""):
                continue
            name = getattr(att, "file_name", None) or (
                att.get("file_name") if isinstance(att, dict) else None
            ) or f"upload_{i}.jpg"
            safe = re.sub(r"[^A-Za-z0-9._-]", "_", Path(str(name)).name) or f"upload_{i}.jpg"
            dest = inbound_dir / safe
            try:
                res = await asyncio.to_thread(download, att, dest)
            except Exception:  # noqa: BLE001
                log.exception("download_attachment failed")
                continue
            if res and res.get("ok") and res.get("path"):
                saved.append(str(res["path"]))
            elif res and res.get("ok") and dest.is_file():
                saved.append(str(dest))
        return saved

    async def _ensure_media_generated(
        self,
        user_text: str,
        workspace: str,
        *,
        session_id: str = "",
        reference_images: list[str] | None = None,
    ) -> dict[str, Any]:
        """Direct Pixio generation into the session workspace (Telegram guarantee).

        Used when media intent was detected but the agent session left no media
        files. When ``reference_images`` is set, runs image-to-video (upload
        still → video model). Never raises — returns ``{ok, error?}``.
        """
        root = Path(workspace or "")
        if not root.is_dir():
            try:
                root.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                return {"ok": False, "error": f"workspace missing: {exc}"}

        platform = getattr(self.orchestrator, "p", None)
        if platform is None:
            return {"ok": False, "error": "no platform on orchestrator"}

        secrets = getattr(platform, "secrets", None)
        key = None
        if secrets is not None:
            try:
                key = secrets.get("pixio") or secrets.get("pixio_api_key")
            except Exception:  # noqa: BLE001
                key = None
        if not key:
            import os

            key = os.environ.get("PIXIO_API_KEY") or None
        if not key:
            return {
                "ok": False,
                "error": (
                    "Pixio API key not configured — add secret 'pixio' "
                    "or set PIXIO_API_KEY"
                ),
            }

        from ..tools.base import ToolContext
        from ..tools.pixio import PixioGenerateTool, PixioModelsTool, PixioUploadTool

        cfg = getattr(platform, "config", None)
        event_bus = getattr(platform, "event_bus", None)
        engine = getattr(platform, "engine", None)
        artifacts = getattr(platform, "artifacts", None)

        def _key_resolver() -> str | None:
            return key

        artifact_sink = None
        if artifacts is not None and hasattr(artifacts, "save"):

            def _sink(
                name: str,
                blob: bytes,
                filename: str,
                kind: str,
                sid: str | None,
            ) -> Any:
                return artifacts.save(
                    name,
                    blob,
                    kind=kind or "file",
                    filename=filename,
                    session_id=sid,
                )

            artifact_sink = _sink

        if cfg is None or event_bus is None or engine is None:
            return {"ok": False, "error": "platform incomplete for media generation"}

        ctx = ToolContext(
            workspace=root,
            session_id=session_id or "comm-media",
            agent_run_id="comm-media-fallback",
            config=cfg,
            event_bus=event_bus,
            engine=engine,
        )

        refs = [p for p in (reference_images or []) if p and Path(p).is_file()]
        kind = self._media_kind(user_text, has_reference_image=bool(refs))

        models_tool = PixioModelsTool(
            key_resolver=_key_resolver, artifact_sink=artifact_sink
        )
        gen_tool = PixioGenerateTool(
            key_resolver=_key_resolver, artifact_sink=artifact_sink
        )

        models_res = await models_tool.execute({}, ctx)
        if not models_res.ok:
            return {"ok": False, "error": models_res.error or "pixio_models failed"}

        model_id = self._pick_pixio_model(
            (models_res.data or {}).get("models") or [],
            kind=kind,
        )
        if not model_id:
            return {"ok": False, "error": "no suitable Pixio model available"}

        prompt = self._media_prompt(user_text)
        params: dict[str, Any] = {"prompt": prompt}

        # Image-to-video: publish the still, pass public URL into common param names.
        if refs and kind == "video":
            upload_tool = PixioUploadTool(
                key_resolver=_key_resolver, artifact_sink=artifact_sink
            )
            up = await upload_tool.execute(
                {"path": refs[0], "endpoint": "images"}, ctx
            )
            if not up.ok:
                # Retry as generic media endpoint.
                up = await upload_tool.execute(
                    {"path": refs[0], "endpoint": "media"}, ctx
                )
            if not up.ok:
                return {
                    "ok": False,
                    "error": up.error or "failed to upload reference image to Pixio",
                }
            public_url = str((up.data or {}).get("url") or "").strip()
            if not public_url:
                return {"ok": False, "error": "pixio_upload returned no public url"}
            # Cover common image-to-video param names across models.
            for key_name in (
                "image",
                "image_url",
                "imageUrl",
                "init_image",
                "initImage",
                "first_frame",
                "firstFrame",
                "url",
                "input_image",
                "reference_image",
            ):
                params[key_name] = public_url

        gen_res = await gen_tool.execute(
            {
                "model_id": model_id,
                "params": params,
                "wait": True,
                "timeout_seconds": 600 if kind == "video" else 300,
            },
            ctx,
        )
        if not gen_res.ok:
            # If the model rejected extra image params, retry video with prompt-only
            # is wrong for i2v — surface the error honestly.
            return {"ok": False, "error": gen_res.error or "pixio_generate failed"}
        return {
            "ok": True,
            "model_id": model_id,
            "kind": kind,
            "saved_path": (gen_res.data or {}).get("saved_path"),
            **({"reference": refs[0]} if refs else {}),
        }

    @staticmethod
    def _pick_pixio_model(models: list[Any], *, kind: str) -> str:
        """Choose a model id from pixio_models output for the requested media kind."""
        if not isinstance(models, list):
            return ""
        rows: list[tuple[str, str, str]] = []
        for model in models:
            if not isinstance(model, dict):
                continue
            mid = str(model.get("id") or model.get("modelId") or "").strip()
            if not mid:
                continue
            name = str(model.get("name") or "").lower()
            mtype = str(model.get("type") or model.get("category") or "").lower()
            rows.append((mid, name, mtype))
        if not rows:
            return ""

        kind = (kind or "image").lower()
        prefer_tokens = {
            "image": ("image", "img", "flux", "sdxl", "sd3", "photo", "illust"),
            "video": ("video", "veo", "runway", "kling", "minimax", "luma", "clip"),
            "audio": ("audio", "music", "song", "sound", "tts", "voice", "suno"),
        }.get(kind, ("image", "flux"))

        def score(row: tuple[str, str, str]) -> int:
            mid, name, mtype = row
            blob = f"{mid} {name} {mtype}".lower()
            s = 0
            for tok in prefer_tokens:
                if tok in blob:
                    s += 10
            # Prefer ids that look like the requested modality in type field.
            if kind in mtype:
                s += 20
            # Mild preference for shorter "default-looking" models.
            if "flux" in blob and kind == "image":
                s += 5
            return s

        rows.sort(key=score, reverse=True)
        best = rows[0]
        if score(best) <= 0 and kind != "image":
            # Fall back to first image-ish model rather than failing hard.
            for row in rows:
                if score(row) > 0 or "image" in f"{row[1]} {row[2]}":
                    return row[0]
        return best[0]

    @staticmethod
    def _media_prompt(user_text: str) -> str:
        """Strip command-y words so the generator gets a clean creative prompt."""
        t = (user_text or "").strip()
        # Drop leading generate/create/make phrases for a cleaner prompt.
        t = re.sub(
            r"(?is)^\s*(please\s+)?(can you\s+|could you\s+)?"
            r"(generate|create|make|draw|render|design|produce|compose)\s+"
            r"(me\s+)?(an?\s+)?(image|picture|photo|pic|art|logo|video|clip|"
            r"song|music|audio|media)\s*(of|for|showing|with|:)?\s*",
            "",
            t,
        ).strip()
        return t or (user_text or "").strip() or "abstract digital art"

    @staticmethod
    def _collect_session_media(
        workspace: str, *, exclude_paths: set[str] | None = None
    ) -> list[Path]:
        """Newest media files under a session workspace (pixio/ + root), capped.

        ``exclude_paths`` skips user-uploaded reference stills so we only attach
        newly generated outputs (not the inbound photo itself).
        """
        root = Path(workspace or "")
        if not root.is_dir():
            return []
        skip: set[str] = set()
        for raw in exclude_paths or set():
            try:
                skip.add(str(Path(raw).resolve()))
            except OSError:
                skip.add(str(raw))
        found: list[Path] = []
        try:
            for p in root.rglob("*"):
                if not p.is_file():
                    continue
                if p.suffix.lower() not in _MEDIA_EXTS:
                    continue
                # Never re-send the user's uploaded reference photo as "output".
                try:
                    if str(p.resolve()) in skip:
                        continue
                    # Also skip anything under inbound/ (download staging).
                    if "inbound" in p.parts:
                        continue
                except OSError:
                    pass
                # Skip huge accidental dumps
                try:
                    if p.stat().st_size <= 0 or p.stat().st_size > 50 * 1024 * 1024:
                        continue
                except OSError:
                    continue
                found.append(p)
        except OSError:
            return []
        found.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        return found[:_MAX_MEDIA_PER_REPLY]

    async def _reply_unauthorized(self, ch: Channel, msg: InboundMessage) -> bool:
        """Tell strangers the bot is owner-gated. Never runs tools/sessions.

        Rate-limited per sender so a public X post cannot turn the bot into a
        denial spam cannon. Returns True when a reply was attempted/sent.
        """
        import time

        sid = str(msg.sender_id)
        now = time.monotonic()
        last = self._unauth_reply_at.get(sid, 0.0)
        if now - last < _UNAUTHORIZED_REPLY_COOLDOWN_S:
            return False
        self._unauth_reply_at[sid] = now
        body = self._format_reply(
            _UNAUTHORIZED_REPLY.format(sender_id=sid)
        )
        try:
            chat_id = msg.reply_to if msg.reply_to is not None else msg.sender_id
            res = await asyncio.to_thread(ch.send, body, chat_id=chat_id)
            return bool(res and res.get("ok"))
        except Exception:  # noqa: BLE001
            log.exception("unauthorized deny reply failed")
            return False

    def _format_reply(self, reply: str) -> str:
        """Always produce a non-empty Telegram message body."""
        body = (reply or "").strip() or "…"
        # Avoid double brand prefix if the payload already includes it.
        prefix = self.reply_prefix or ""
        if body.startswith(prefix.strip()) or body.startswith("Epic Tech AI"):
            text = body
        else:
            text = f"{prefix}{body}"
        return text[: self.max_reply_chars]

    async def _publish(self, etype: str, payload: dict[str, Any], **kw: Any) -> None:
        if self.event_bus is None:
            return
        try:
            await self.event_bus.publish(etype, payload, **kw)
        except Exception:  # noqa: BLE001 — the event bus must never block comm
            log.exception("failed to publish %s", etype)
