#!/usr/bin/env python3
"""Apply full Epic Tech AI brand to the Telegram bot profile.

Uses TELEGRAM_BOT_TOKEN from gitignored .env or the vault.
Never prints the token.

  uv run python scripts/brand_telegram_profile.py
  uv run python scripts/brand_telegram_profile.py --photo desktop/assets/icon.png
"""

from __future__ import annotations

import argparse
import json
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


def _token() -> str | None:
    t = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if t:
        return t
    sys.path.insert(0, str(ROOT / "src"))
    try:
        from iron_jarvis.platform import build_platform

        p = build_platform(str(ROOT))
        return (
            p.secrets.get("telegram_bot_token")
            or p.secrets.get("channel_epic_token")
            or None
        )
    except Exception:  # noqa: BLE001
        return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--photo",
        type=Path,
        default=ROOT / "desktop" / "assets" / "epic-tech-ai-bot-avatar.png",
        help="Profile photo (PNG/JPG, square preferred) — Epic Tech AI brand mark",
    )
    parser.add_argument("--skip-photo", action="store_true")
    args = parser.parse_args()

    _load_dotenv()
    token = _token()
    if not token:
        print("ERROR: no TELEGRAM_BOT_TOKEN in .env or vault")
        return 1

    from iron_jarvis.brand import (
        CONTACT_EMAIL,
        CONTACT_X_HANDLE,
        PRODUCT_NAME,
        PRODUCT_TAGLINE,
        TELEGRAM_BOT_DISPLAY_NAME,
    )

    base = f"https://api.telegram.org/bot{token}"
    cmds = [
        {"command": "help", "description": "Command list"},
        {"command": "status", "description": "Version, model, live work"},
        {"command": "workflows", "description": "List saved workflows"},
        {"command": "run", "description": "Start workflow: /run <name>"},
        {"command": "runs", "description": "Recent workflow runs"},
        {"command": "cancel", "description": "Stop a run: /cancel <id>"},
        {"command": "agents", "description": "List remote agents"},
        {"command": "ask", "description": "Ask agent: /ask <agent> <task>"},
        {"command": "sessions", "description": "Recent sessions"},
        {"command": "balance", "description": "Credit balance"},
        {"command": "buy", "description": "Credit packs / checkout"},
        {"command": "usage", "description": "Token usage summary"},
    ]

    description = (
        f"{PRODUCT_NAME} — {PRODUCT_TAGLINE} "
        f"Message me tasks, /status, /run workflows, /balance. "
        f"Contact {CONTACT_EMAIL} · {CONTACT_X_HANDLE}"
    )
    short = f"{PRODUCT_NAME} · local-first AI OS · agents & workflows"

    jobs: list[tuple[str, dict]] = [
        ("setMyName", {"name": TELEGRAM_BOT_DISPLAY_NAME}),
        ("setMyDescription", {"description": description[:512]}),
        ("setMyShortDescription", {"short_description": short[:120]}),
        ("setMyCommands", {"commands": cmds}),
    ]

    with httpx.Client(timeout=30.0) as client:
        me = client.get(f"{base}/getMe").json()
        if not me.get("ok"):
            print("ERROR: getMe failed — token invalid or revoked")
            return 1
        username = me["result"].get("username")
        print(f"Bot: @{username} → branding as {TELEGRAM_BOT_DISPLAY_NAME}")

        for method, payload in jobs:
            r = client.post(f"{base}/{method}", json=payload)
            j = r.json()
            print(f"  {method}: {'ok' if j.get('ok') else j}")

        if not args.skip_photo and args.photo.is_file():
            # Bot API: InputProfilePhotoStatic via attach://
            meta = json.dumps({"type": "static", "photo": "attach://pic"})
            files = {
                "photo": (None, meta, "application/json"),
                "pic": (args.photo.name, args.photo.read_bytes(), "image/png"),
            }
            # httpx multipart: mix of data fields
            r = client.post(
                f"{base}/setMyProfilePhoto",
                data={"photo": meta},
                files={"pic": (args.photo.name, args.photo.read_bytes(), "image/png")},
            )
            j = r.json()
            if j.get("ok"):
                print(f"  setMyProfilePhoto: ok ({args.photo.name})")
            else:
                # Fallback: some API versions want pure file under photo=
                r2 = client.post(
                    f"{base}/setMyProfilePhoto",
                    files={"photo": (args.photo.name, args.photo.read_bytes(), "image/png")},
                )
                j2 = r2.json()
                print(
                    f"  setMyProfilePhoto: "
                    f"{'ok' if j2.get('ok') else j2.get('description') or j2}"
                )
        elif not args.skip_photo:
            print(f"  setMyProfilePhoto: skipped (missing {args.photo})")

    print(f"Open: https://t.me/{username}")
    print("Tip: reopen the chat or clear cache if Telegram still shows the old name.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
