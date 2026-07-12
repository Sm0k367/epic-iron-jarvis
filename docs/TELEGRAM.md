# Epic Tech AI — Telegram bot setup

Drive the platform from your phone: commands, workflows, sessions, credits.

## What it will be named

| Layer | Recommended name | Notes |
|-------|------------------|--------|
| **Telegram display name** | **Epic Tech AI** | What people see in the chat header |
| **Telegram username** | **`@EpicTechAI_bot`** | Must end in `bot`; must be unique on Telegram. If taken, try `@EpicTechAIBot`, `@Epic_Tech_AI_bot`, `@EpicTechAI_OS_bot` |
| **Dashboard channel name** | `epic` or `tg` | Internal id (a–z, no spaces) when adding the channel |
| **Reply prefix** | `Epic Tech AI: ` | Automatic on every bot reply |

You choose the username when creating the bot with **@BotFather**. The software brand is always **Epic Tech AI**.

## Prerequisites

1. Epic Tech AI daemon running (`uv run ironjarvis up` or desktop app / tray)
2. A Telegram account
3. Your numeric Telegram user id (for the allowlist)

## Step-by-step

### 1 · Create the bot (BotFather)

1. Open Telegram → search **`@BotFather`** → Start.
2. Send `/newbot`.
3. **Name (display):** `Epic Tech AI`
4. **Username:** e.g. `EpicTechAI_bot` → Telegram registers **`@EpicTechAI_bot`**
5. Copy the **HTTP API token** (looks like `123456:ABC-DEF...`).
   - Store it only in Secrets / the channel form — **never commit it**.

### Brand the profile (name, about, photo, commands)

From the repo (uses token from `.env` / vault — never prints it):

```powershell
uv run python scripts/brand_telegram_profile.py
# optional custom photo:
uv run python scripts/brand_telegram_profile.py --photo path\to\logo.png
```

This sets **Epic Tech AI** display name, description, about, command menu, and
profile photo (`desktop/assets/epic-tech-ai-bot-avatar.png` by default — cyan
arc-reactor **E** mark, high contrast for small chat lists).

Or via BotFather:

```
/setname — Epic Tech AI
/setdescription — Local-first AI OS · agents, workflows, credits · Epic Tech AI
/setabouttext — epictechai@gmail.com · x.com/EpicTechAI
/setuserpic — your Epic Tech AI logo
/setcommands — paste the command list below
```

Suggested `/setcommands` list:

```
status - Version, model, live work
workflows - List saved workflows
run - Start a workflow: /run <name>
runs - Recent workflow runs
cancel - Stop a run: /cancel <id>
agents - List remote agents
ask - Ask a remote agent: /ask <agent> <task>
sessions - Recent sessions
balance - Credit balance
buy - Credit packs / checkout
usage - Token usage summary
help - Command list
```

### 2 · Find your user id (allowlist)

Message **`@userinfobot`** or **`@getidsbot`** and copy your numeric **Id**.  
For private DMs this is usually the same as **chat id**.

### 3 · Add the channel in Epic Tech AI

**Dashboard → Channels → Add channel**

| Field | Value |
|-------|--------|
| **Name** | `epic` (or `tg`) |
| **Type** | `telegram` |
| **Bot token** | paste from BotFather (stored encrypted) |
| **Default chat ID** | your numeric id (outbound alerts) |
| **Enable two-way** | `true` |
| **Allowlist** | your numeric user id only (comma-separated if multiple) |

Save, then **Send test** with a short message. You should receive it in Telegram.

### 4 · Keep the daemon online

Two-way mode **long-polls** Telegram. Closing the desktop window is fine if it stays in the **system tray**; fully quitting the app stops the bot.

### 5 · Talk to the bot

Open a private chat with **`@EpicTechAI_bot`** (or whatever username you registered).

| You send | Bot does |
|----------|----------|
| `/help` | Command list |
| `/status` | Version, model, live work |
| `/balance` | Credit balance |
| `/buy` | Credit pack list |
| `/run nightly` | Start saved workflow `nightly` |
| Free text | Supervised agent session → summary reply |

Replies look like: **`Epic Tech AI: …`**

## Media generation (images / video / audio)

When an **allowlisted** user asks the bot to generate media in free text, e.g.:

- `generate an image of a red fox`
- `create a logo for my brand`
- `make a video of ocean waves`
- `compose a song about rain`

### Photo → video (image-to-video)

1. Send a **photo** (or image document) in the private chat  
2. Caption it, e.g. `make a video of this` / `animate this` / `bring this to life`  
3. Photo-only (no caption) defaults to: animate the still into a short video  

Epic Tech AI will download the still, run **image-to-video** via Pixio
(`pixio_upload` of the photo → video model → `pixio_generate`), and **attach
the video** on the reply. The original upload is not re-sent as the “result”.

Epic Tech AI will:

1. Run a full agent session with **required** Pixio tools (`pixio_models` → `pixio_params` → `pixio_generate`; plus `pixio_upload` when a photo is attached)
2. If the agent finishes **without** media files, run a **direct Pixio fallback** into the session workspace (image-to-video when a photo was uploaded)
3. **Attach** generated files on the Telegram reply (`sendPhoto` / `sendVideo` / `sendAudio` / document)

**Required for media:** a Pixio key in the vault.

| Place | Secret name |
|-------|-------------|
| Secrets / Connections | `pixio` |
| `.env` (bootstrap) | `PIXIO_API_KEY` → loaded as vault `pixio` |

```powershell
# after setting PIXIO_API_KEY in .env:
uv run python scripts/load_env_to_vault.py
# restart the daemon so Telegram + tools see the key
```

Without Pixio, the bot replies with a clear error instead of silently skipping media.

## Safety (built-in)

- **Inbound off** until you set `inbound_enabled=true`
- **Allowlist fail-closed** — empty list = nobody can command the bot
- **Private chat only** — group messages that would broadcast to others are refused
- Bot messages ignored (no loops)
- Agent tools still pass the normal permission engine
- Media generation only for allowlisted private chats (never groups / unauthorized)

Never add untrusted user ids to the allowlist. Never put the bot token in git or public issues.

## Secrets via `.env` (optional)

```env
# gitignored — never commit
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
TELEGRAM_ALLOWED_SENDERS=
```

Then prefer Dashboard → Channels (or vault names) so the notifier wires the channel on boot. The Channels UI path above is the supported few-click flow.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| No replies | Daemon running? `inbound_enabled=true`? Your id in allowlist? |
| Test send fails | Token valid? Chat id correct? You must have started a chat with the bot once |
| 409 getUpdates conflict | Only one poller — don't run two daemons with the same token |
| Commands work, free text doesn't | Provider connected? Check Connections + Usage |
| Text reply but no image/video | Connect **Pixio** (`pixio` secret / `PIXIO_API_KEY`); restart daemon; ask again with “generate an image of …” |

## Related

- [REFLEX.md](./REFLEX.md) — phone command grammar + ambient rules  
- [TOKEN-POLICY.md](./TOKEN-POLICY.md) — never hardcode tokens  
- [legal/PRIVACY.md](../legal/PRIVACY.md) — messaging / third-party processing  

**Contact:** epictechai@gmail.com · [@EpicTechAI](https://x.com/EpicTechAI)
