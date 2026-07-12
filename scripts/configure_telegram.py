#!/usr/bin/env python3
"""Wire Telegram channel for Epic Tech AI from vault/env (never prints the token).

Usage:
  # After TELEGRAM_BOT_TOKEN is in .env / vault:
  uv run python scripts/configure_telegram.py

  # With your numeric user id (from @userinfobot):
  uv run python scripts/configure_telegram.py --user-id 123456789

  # Or let getUpdates discover the last private chat (message the bot first):
  uv run python scripts/configure_telegram.py --from-updates
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


def _load_dotenv() -> None:
    env_path = ROOT / ".env"
    if not env_path.is_file():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip().strip("'").strip('"')
        if k and not os.environ.get(k):
            os.environ[k] = v


def main() -> int:
    parser = argparse.ArgumentParser(description="Configure Epic Tech AI Telegram channel")
    parser.add_argument("--user-id", type=str, default="", help="Your Telegram user id (allowlist + chat_id)")
    parser.add_argument(
        "--from-updates",
        action="store_true",
        help="Discover chat/user id from getUpdates (you must /start the bot first)",
    )
    parser.add_argument("--name", default="epic", help="Channel registration name (default: epic)")
    parser.add_argument("--no-inbound", action="store_true", help="Outbound alerts only")
    args = parser.parse_args()

    _load_dotenv()
    sys.path.insert(0, str(ROOT / "src"))
    from iron_jarvis.platform import build_platform
    from iron_jarvis.core.config import persist_config_values
    from iron_jarvis.comm import CHANNEL_TYPES, httpx_get, httpx_post
    from iron_jarvis.brand import (
        PRODUCT_NAME,
        TELEGRAM_BOT_DISPLAY_NAME,
        TELEGRAM_BOT_USERNAME_HINT,
    )

    platform = build_platform(str(ROOT))
    token = (
        os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        or platform.secrets.get("telegram_bot_token")
        or platform.secrets.get("channel_epic_token")
    )
    if not token:
        print("ERROR: no TELEGRAM_BOT_TOKEN in .env or vault. Add it then re-run.")
        return 1

    # Verify token (never print it)
    try:
        r = httpx.get(f"https://api.telegram.org/bot{token}/getMe", timeout=15.0)
        data = r.json()
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: getMe failed: {type(exc).__name__}: {exc}")
        return 1
    if not data.get("ok"):
        print(f"ERROR: getMe rejected token: {data.get('description', data)}")
        return 1
    me = data["result"]
    username = me.get("username") or TELEGRAM_BOT_USERNAME_HINT
    print(f"Bot OK: @{username} (id={me.get('id')}) — brand: {TELEGRAM_BOT_DISPLAY_NAME}")

    user_id = (args.user_id or os.environ.get("TELEGRAM_CHAT_ID") or os.environ.get("TELEGRAM_ALLOWED_SENDERS") or "").strip()
    if args.from_updates or not user_id:
        try:
            ur = httpx.get(
                f"https://api.telegram.org/bot{token}/getUpdates",
                params={"timeout": 0},
                timeout=20.0,
            )
            updates = ur.json()
        except Exception as exc:  # noqa: BLE001
            print(f"WARN: getUpdates failed: {exc}")
            updates = {}
        if updates.get("ok"):
            for upd in reversed(updates.get("result") or []):
                msg = upd.get("message") or upd.get("edited_message") or {}
                frm = msg.get("from") or {}
                chat = msg.get("chat") or {}
                if frm.get("id") and not frm.get("is_bot"):
                    user_id = str(frm["id"])
                    print(f"Discovered sender/chat id from updates: {user_id}")
                    break
                if chat.get("id") and chat.get("type") == "private":
                    user_id = str(chat["id"])
                    print(f"Discovered private chat id from updates: {user_id}")
                    break

    if not user_id:
        print(
            "\nAlmost done. Message your bot on Telegram (open t.me/"
            f"{username} and send /start), then re-run:\n"
            "  uv run python scripts/configure_telegram.py --from-updates\n"
            "Or pass your id explicitly:\n"
            "  uv run python scripts/configure_telegram.py --user-id YOUR_ID\n"
            "(Get id from @userinfobot)\n"
        )
        # Still store secret for later
        secret_name = f"channel_{args.name}_token"
        platform.secrets.set(secret_name, token, kind="token")
        platform.secrets.set("telegram_bot_token", token, kind="token")
        print(f"Token stored in vault as {secret_name} + telegram_bot_token (len={len(token)})")
        return 2

    secret_name = f"channel_{args.name}_token"
    platform.secrets.set(secret_name, token, kind="token")
    platform.secrets.set("telegram_bot_token", token, kind="token")

    inbound = not args.no_inbound
    config = {
        "type": "telegram",
        "token_secret": secret_name,
        "chat_id": user_id,
        "inbound_enabled": inbound,
        "allowed_senders": [user_id] if inbound else [],
    }

    comm = dict(platform.config.comm or {})
    channels = dict(comm.get("channels") or {})
    channels[args.name] = config
    comm["channels"] = channels
    platform.config.comm = comm
    persist_config_values(platform.config.home, {"comm": comm})

    # Live-register so a running-style test works without restart of this process
    channel = CHANNEL_TYPES["telegram"](
        config,
        http_post=httpx_post,
        http_get=httpx_get,
        secret_resolver=platform.secrets.get,
    )
    platform.notifier.add_channel(args.name, channel)

    send = channel.send(
        f"{PRODUCT_NAME} is online. Two-way={'on' if inbound else 'off'}. "
        f"Try /help · t.me/{username}"
    )
    print(f"Channel '{args.name}' configured. inbound={inbound} allowlist=[{user_id}]")
    print(f"Test send: ok={send.get('ok')} detail={send.get('detail')}")
    print(f"Config home: {platform.config.home}")
    print("Restart the daemon (ironjarvis up) so the inbound poller loads this channel.")
    print(f"Chat: https://t.me/{username}")
    return 0 if send.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
