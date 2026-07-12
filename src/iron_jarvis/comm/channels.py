"""Concrete communication channels.

Every channel builds its own target URL + JSON payload and delegates the POST to
the injected ``http_post`` callable (see :mod:`.base`), so no real network is
touched in tests. Missing token / url / chat-id yields ``ok=False`` with a clear
``detail`` rather than raising.

``MockChannel`` is the offline default — it records every message in ``.sent``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..core.logging import get_logger
from .base import Channel, InboundAttachment, InboundMessage

_log = get_logger("comm")

#: Telegram Bot API media limits (bytes) — stay under documented caps.
_TG_PHOTO_MAX = 10 * 1024 * 1024
_TG_DOC_MAX = 50 * 1024 * 1024
_TG_DOWNLOAD_MAX = 20 * 1024 * 1024  # inbound download cap (image-to-video refs)
_TG_PHOTO_EXTS = frozenset({".jpg", ".jpeg", ".png", ".gif", ".webp"})
_TG_VIDEO_EXTS = frozenset({".mp4", ".webm", ".mov"})
_TG_AUDIO_EXTS = frozenset({".mp3", ".wav", ".ogg", ".m4a"})
_TG_INBOUND_IMAGE_EXTS = frozenset({".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"})

SLACK_POST_MESSAGE_URL = "https://slack.com/api/chat.postMessage"
TELEGRAM_API = "https://api.telegram.org"


class SlackChannel(Channel):
    """Slack via incoming webhook *or* ``chat.postMessage`` with a bot token.

    config:
      * ``{"webhook_url": "..."}`` — posts ``{"text": message}`` to the webhook, or
      * ``{"token_secret": "...", "channel": "#general"}`` — resolves the bot
        token by name and calls ``chat.postMessage`` (token carried in payload so
        it works with the (url, json)-only transport contract).
    """

    name = "slack"
    #: Socket Mode gives Slack a receive leg (outbound WebSocket — no public
    #: URL needed); the inbound pipeline gates on inbound_enabled + allowlist.
    supports_inbound = True

    def send(self, message: str, **kw: Any) -> dict[str, Any]:
        # `chat_id` is the inbound pipeline's reply address (a Slack user id —
        # chat.postMessage with channel=U… delivers to that user's DM). When
        # present, prefer the token path so the reply reaches the SENDER
        # instead of the configured broadcast target.
        reply_target = kw.get("chat_id")
        token_secret = self.config.get("token_secret")
        if token_secret and (reply_target or not self.config.get("webhook_url")):
            token = self._resolve_secret(token_secret)
            if not token:
                return self._fail(f"slack: token secret '{token_secret}' did not resolve")
            channel = reply_target or kw.get("channel") or self.config.get("channel")
            if not channel:
                return self._fail("slack: chat.postMessage requires a `channel`")
            payload = {"channel": channel, "text": message, "token": token}
            return self._post(SLACK_POST_MESSAGE_URL, payload)

        webhook = self.config.get("webhook_url")
        if webhook:
            return self._post(webhook, {"text": message})

        return self._fail("slack: config needs `webhook_url` or `token_secret`+`channel`")


class DiscordChannel(Channel):
    """Discord via incoming webhook. config: ``{"webhook_url": "..."}``."""

    name = "discord"

    def send(self, message: str, **kw: Any) -> dict[str, Any]:
        webhook = self.config.get("webhook_url")
        if not webhook:
            return self._fail("discord: config needs `webhook_url`")
        return self._post(webhook, {"content": message})


class TelegramChannel(Channel):
    """Telegram Bot API ``sendMessage`` (outbound) + ``getUpdates`` (inbound).

    config: ``{"token_secret": "...", "chat_id": 123456}`` plus the optional
    two-way fields ``inbound_enabled`` (bool) and ``allowed_senders`` (list of
    Telegram user/chat ids). Inbound is OFF unless ``inbound_enabled`` is set.
    """

    name = "telegram"
    supports_inbound = True

    def send(self, message: str, **kw: Any) -> dict[str, Any]:
        token_secret = self.config.get("token_secret")
        token = self._resolve_secret(token_secret)
        if not token:
            return self._fail(
                f"telegram: token secret '{token_secret}' did not resolve"
                if token_secret
                else "telegram: config needs `token_secret`"
            )
        chat_id = kw.get("chat_id") or self.config.get("chat_id")
        if not chat_id:
            return self._fail("telegram: config needs `chat_id`")
        url = f"{TELEGRAM_API}/bot{token}/sendMessage"
        payload: dict[str, Any] = {"chat_id": chat_id, "text": message}
        # Optional Telegram formatting (MarkdownV2 / HTML) when callers request it.
        parse_mode = kw.get("parse_mode")
        if parse_mode:
            payload["parse_mode"] = parse_mode
        return self._post(url, payload)

    def send_media(
        self,
        path: str | Path,
        *,
        chat_id: Any = None,
        caption: str = "",
        kind: str | None = None,
    ) -> dict[str, Any]:
        """Upload a local file via sendPhoto / sendVideo / sendAudio / sendDocument.

        Uses multipart form (not the JSON http_post path). Caps size to Telegram
        limits. ``kind`` auto-detected from extension when omitted.
        """
        token_secret = self.config.get("token_secret")
        token = self._resolve_secret(token_secret)
        if not token:
            return self._fail("telegram: no token for media")
        cid = chat_id if chat_id is not None else self.config.get("chat_id")
        if not cid:
            return self._fail("telegram: no chat_id for media")
        p = Path(path)
        if not p.is_file():
            return self._fail(f"telegram: media not found: {p}")
        try:
            size = p.stat().st_size
        except OSError as exc:
            return self._fail(f"telegram: cannot stat media: {exc}")
        ext = p.suffix.lower()
        mode = (kind or "").lower().strip()
        if not mode:
            if ext in _TG_PHOTO_EXTS:
                mode = "photo"
            elif ext in _TG_VIDEO_EXTS:
                mode = "video"
            elif ext in _TG_AUDIO_EXTS:
                mode = "audio"
            else:
                mode = "document"
        max_bytes = _TG_PHOTO_MAX if mode == "photo" else _TG_DOC_MAX
        if size > max_bytes:
            return self._fail(
                f"telegram: {p.name} is {size} bytes (max {max_bytes} for {mode})"
            )
        method = {
            "photo": "sendPhoto",
            "video": "sendVideo",
            "audio": "sendAudio",
            "document": "sendDocument",
        }.get(mode, "sendDocument")
        field = {
            "photo": "photo",
            "video": "video",
            "audio": "audio",
            "document": "document",
        }.get(mode, "document")
        url = f"{TELEGRAM_API}/bot{token}/{method}"
        data = {"chat_id": str(cid)}
        cap = (caption or "").strip()
        if cap:
            data["caption"] = cap[:1024]
        try:
            import httpx

            with p.open("rb") as fh:
                files = {field: (p.name, fh)}
                resp = httpx.post(
                    url,
                    data=data,
                    files=files,
                    timeout=httpx.Timeout(120.0, connect=10.0),
                )
            ok = 200 <= int(resp.status_code) < 300
            detail = f"HTTP {resp.status_code}"
            if not ok:
                detail = f"HTTP {resp.status_code}: {(resp.text or '')[:200]}"
            return {"ok": ok, "detail": detail, "method": method, "path": str(p)}
        except Exception as exc:  # noqa: BLE001 — never break the inbound loop
            return {"ok": False, "detail": f"{type(exc).__name__}: {exc}"}

    def typing(self, chat_id: Any = None) -> dict[str, Any]:
        """Show the Telegram 'typing…' indicator (lasts ~5s on the client)."""
        token_secret = self.config.get("token_secret")
        token = self._resolve_secret(token_secret)
        if not token:
            return self._fail("telegram: no token for typing")
        cid = chat_id if chat_id is not None else self.config.get("chat_id")
        if not cid:
            return self._fail("telegram: no chat_id for typing")
        url = f"{TELEGRAM_API}/bot{token}/sendChatAction"
        return self._post(url, {"chat_id": cid, "action": "typing"})

    def poll(
        self, offset: int = 0, *, timeout: int = 0
    ) -> tuple[list[InboundMessage], int]:
        """Long-poll ``getUpdates`` and parse text + photo/document messages.

        Photos (and image documents) are accepted so users can upload a still
        and ask for a video. Caption is treated as the user text when present.
        Passing ``offset`` confirms (and so DROPS server-side) every update with
        a lower id, which is what makes the durable offset dedupe across
        restarts. Returns ``(messages, next_offset)`` where ``next_offset`` is
        ``max(update_id) + 1``; on any failure returns ``([], offset)``.
        """
        token = self._resolve_secret(self.config.get("token_secret"))
        if not token:
            return [], offset
        url = f"{TELEGRAM_API}/bot{token}/getUpdates"
        params: dict[str, Any] = {"timeout": timeout}
        if offset:
            params["offset"] = offset
        data = self._get_json(url, params)
        if not data or not data.get("ok"):
            return [], offset

        messages: list[InboundMessage] = []
        next_offset = offset
        for upd in data.get("result", []) or []:
            update_id = upd.get("update_id")
            if isinstance(update_id, int):
                next_offset = max(next_offset, update_id + 1)
            msg = upd.get("message") or upd.get("edited_message") or {}
            text = (msg.get("text") or msg.get("caption") or "").strip()
            attachments = self._extract_attachments(msg)
            if not text and not attachments:
                continue  # ignore joins, stickers without caption, etc.
            frm = msg.get("from") or {}
            chat = msg.get("chat") or {}
            messages.append(
                InboundMessage(
                    sender_id=str(frm.get("id", "")),
                    text=text,
                    update_id=update_id,
                    reply_to=chat.get("id"),
                    is_bot=bool(frm.get("is_bot", False)),
                    raw=upd,
                    attachments=attachments,
                )
            )
        return messages, next_offset

    @staticmethod
    def _extract_attachments(msg: dict[str, Any]) -> list[InboundAttachment]:
        """Pull photo / image-document file_ids from a Telegram message payload."""
        out: list[InboundAttachment] = []
        photos = msg.get("photo") or []
        if isinstance(photos, list) and photos:
            # Telegram sends several sizes; take the largest (last).
            best = photos[-1] if isinstance(photos[-1], dict) else {}
            fid = str(best.get("file_id") or "").strip()
            if fid:
                out.append(
                    InboundAttachment(
                        file_id=fid,
                        kind="photo",
                        file_unique_id=str(best.get("file_unique_id") or ""),
                        file_name="photo.jpg",
                        mime_type="image/jpeg",
                        file_size=int(best.get("file_size") or 0),
                    )
                )
        doc = msg.get("document")
        if isinstance(doc, dict):
            mime = str(doc.get("mime_type") or "").lower()
            name = str(doc.get("file_name") or "document")
            ext = Path(name).suffix.lower()
            is_image = mime.startswith("image/") or ext in _TG_INBOUND_IMAGE_EXTS
            if is_image:
                fid = str(doc.get("file_id") or "").strip()
                if fid:
                    out.append(
                        InboundAttachment(
                            file_id=fid,
                            kind="document",
                            file_unique_id=str(doc.get("file_unique_id") or ""),
                            file_name=name or "upload.png",
                            mime_type=mime or "application/octet-stream",
                            file_size=int(doc.get("file_size") or 0),
                        )
                    )
        return out

    def download_attachment(
        self, attachment: InboundAttachment | dict[str, Any], dest: str | Path
    ) -> dict[str, Any]:
        """Download a Telegram file_id to ``dest`` via getFile + file path.

        Returns ``{"ok": bool, "path"?: str, "detail": str}``. Uses the injected
        ``http_get`` for getFile metadata; the binary body is fetched with a
        direct GET (httpx) because the DI transport is JSON-oriented.
        """
        if isinstance(attachment, InboundAttachment):
            file_id = attachment.file_id
            preferred_name = attachment.file_name or "upload.bin"
        else:
            file_id = str(attachment.get("file_id") or "").strip()
            preferred_name = str(attachment.get("file_name") or "upload.bin")
        if not file_id:
            return self._fail("telegram: attachment missing file_id")
        token = self._resolve_secret(self.config.get("token_secret"))
        if not token:
            return self._fail("telegram: no token for download")
        meta = self._get_json(
            f"{TELEGRAM_API}/bot{token}/getFile", {"file_id": file_id}
        )
        if not meta or not meta.get("ok"):
            return self._fail(
                f"telegram: getFile failed ({(meta or {}).get('description') or 'no response'})"
            )
        result = meta.get("result") or {}
        remote_path = str(result.get("file_path") or "").strip()
        if not remote_path:
            return self._fail("telegram: getFile returned no file_path")
        size = int(result.get("file_size") or 0)
        if size and size > _TG_DOWNLOAD_MAX:
            return self._fail(
                f"telegram: file too large ({size} bytes, max {_TG_DOWNLOAD_MAX})"
            )
        file_url = f"{TELEGRAM_API}/file/bot{token}/{remote_path}"
        dest_path = Path(dest)
        # If dest is a directory, place the file under a safe name.
        if dest_path.exists() and dest_path.is_dir():
            name = Path(remote_path).name or preferred_name or "upload.bin"
            dest_path = dest_path / name
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            import httpx

            resp = httpx.get(
                file_url,
                timeout=httpx.Timeout(120.0, connect=10.0),
                follow_redirects=True,
            )
            status = int(resp.status_code)
            if not 200 <= status < 300:
                return self._fail(f"telegram: file download HTTP {status}")
            blob = bytes(resp.content or b"")
            if not blob:
                return self._fail("telegram: empty file download")
            if len(blob) > _TG_DOWNLOAD_MAX:
                return self._fail(
                    f"telegram: downloaded file too large ({len(blob)} bytes)"
                )
            dest_path.write_bytes(blob)
            return {
                "ok": True,
                "path": str(dest_path),
                "detail": f"saved {len(blob)} bytes",
                "bytes": len(blob),
            }
        except Exception as exc:  # noqa: BLE001 — never break the inbound loop
            return {"ok": False, "detail": f"{type(exc).__name__}: {exc}"}


class MockChannel(Channel):
    """Offline default — records every sent message in :attr:`sent`; always ok."""

    name = "mock"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.sent: list[str] = []
        self.media: list[dict[str, Any]] = []

    def send(self, message: str, **kw: Any) -> dict[str, Any]:
        self.sent.append(message)
        return {"ok": True, "detail": f"recorded ({len(self.sent)})"}

    def send_media(
        self, path: str | Path, *, chat_id: Any = None, caption: str = "", kind: str | None = None
    ) -> dict[str, Any]:
        self.media.append(
            {"path": str(path), "chat_id": chat_id, "caption": caption, "kind": kind}
        )
        return {"ok": True, "detail": f"media-recorded ({len(self.media)})"}


class ConsoleChannel(Channel):
    """Logs/prints the message locally; always ok. Useful as a safe fallback."""

    name = "console"

    def send(self, message: str, **kw: Any) -> dict[str, Any]:
        line = f"[iron-jarvis] {message}"
        _log.info("console notify: %s", message)
        print(line)
        return {"ok": True, "detail": "printed"}


class EmailChannel(Channel):
    """Email via SMTP.

    config: ``{"host": "smtp.gmail.com", "port": 587, "username": "...",
    "password_secret": "...", "from_addr": "...", "to_addr": "...",
    "use_tls": true, "subject": "..."}``. The password is resolved from the vault
    by name (never stored in config). smtplib is imported lazily inside
    :meth:`send` so the comm package still imports where it's unavailable and
    tests that don't send never touch the network.
    """

    name = "email"

    def send(self, message: str, **kw: Any) -> dict[str, Any]:
        cfg = self.config
        host = cfg.get("host")
        from_addr = cfg.get("from_addr") or cfg.get("username")
        to_addr = kw.get("to") or cfg.get("to_addr")
        if not host or not from_addr or not to_addr:
            return self._fail("email: config needs `host`, `from_addr` and `to_addr`")
        password = self._resolve_secret(cfg.get("password_secret"))
        try:
            import smtplib
            from email.message import EmailMessage

            msg = EmailMessage()
            msg["Subject"] = kw.get("subject") or cfg.get("subject") or "Epic Tech AI"
            msg["From"] = from_addr
            msg["To"] = to_addr
            msg.set_content(message)
            port = int(cfg.get("port") or 587)
            with smtplib.SMTP(host, port, timeout=15) as smtp:
                if cfg.get("use_tls", True):
                    smtp.starttls()
                if cfg.get("username") and password:
                    smtp.login(cfg["username"], password)
                smtp.send_message(msg)
            return {"ok": True, "detail": f"emailed {to_addr}"}
        except Exception as exc:  # noqa: BLE001 — surface, never raise to the notifier
            return self._fail(f"email: {type(exc).__name__}: {exc}")


#: registry of channel-type name -> class, for config-driven construction.
CHANNEL_TYPES: dict[str, type[Channel]] = {
    cls.name: cls
    for cls in (
        SlackChannel,
        DiscordChannel,
        TelegramChannel,
        EmailChannel,
        MockChannel,
        ConsoleChannel,
    )
}
