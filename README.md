<div align="center">

# ⚡ Epic Tech AI

### Local-first AI operating system · agents · Telegram · credits

**Agents that plan, build, review, schedule, remember, and ship — on *your* machine, under *your* control.**

No cloud lock-in. No black boxes. Every action logged, every secret encrypted at rest.

**Brand:** Epic Tech AI  
**Email:** [epictechai@gmail.com](mailto:epictechai@gmail.com)  
**X:** [@EpicTechAI](https://x.com/EpicTechAI)  
**Repo:** [Sm0k367/epic-iron-jarvis](https://github.com/Sm0k367/epic-iron-jarvis)

</div>

---

> **TL;DR** — Epic Tech AI is a full AI operating system: multi-agent orchestration, sandboxed worktrees, projects, creative studio, workflows, memory fabric, Reflex phone commands, connector marketplace, **credits ledger**, and a Next.js control center. Runs **fully offline** with a mock model; connect Anthropic / OpenAI / Google / **xAI** / **Groq** / OpenRouter / Ollama via the vault.

> **Core engine** is based on [Iron Jarvis](https://github.com/RealDealCPA-VR/Iron-Jarvis) (credit: RealDealCPA-VR). Product brand and commerce layer: **Epic Tech AI**.

> **Platform:** Windows desktop installer + from-source on Windows/macOS/Linux (`uv` + `npm`).

<div align="center">

![Overview](dashboard/proof/overview-v2.png)

</div>

---

## 🔥 Why Epic Tech AI

- **OS, not a chatbot** — Supervisor → specialist subagents in isolated workspaces.
- **You stay in control** — Fail-closed permissions; git review never auto-merges.
- **It remembers** — Layered memory, LTM, Memory Fabric, lessons that improve over time.
- **Phone-ready** — Telegram / Slack / Discord channels + Reflex `/commands`.
- **Monetizable** — Credits ledger, Stripe checkout hooks, usage metering (keys never hardcoded).
- **Local-first** — SQLite by default; secrets in an encrypted vault; network optional.

---

## ✨ Highlights

| | |
|---|---|
| 🧠 **Multi-agent orchestration** | Supervisor → subagents, isolated context |
| 🔒 **Fail-closed permissions** | allow / ask / deny on every tool |
| 🌳 **Git-native sessions** | branch → work → **you approve** → merge |
| 🧩 **n8n-style workflows** | visual canvas; agents can author them too |
| 🎙️ **Voice chat** | mic + spoken replies (desktop capable) |
| 🗝️ **Encrypted secrets vault** | API keys never shown to agents or the UI |
| 💰 **Credits + billing** | ledger, packs, Stripe (env/vault secrets only) |
| 📱 **Telegram bot commands** | `/status` `/run` `/balance` `/buy` `/usage` … |
| 🔌 **Many models** | Anthropic, OpenAI, Google, xAI, Groq, OpenRouter, Ollama, custom |
| 🛒 **Connector marketplace** | one-tap MCP / OAuth / API connectors |
| 📁 **Projects + Creative Studio** | workspaces, knowledge, media generation |
| 🕰️ **Audit + time-travel undo** | Activity timeline; undo reversible actions |
| 🪟 **Desktop app** | Electron + tray always-on |
| ✅ **Offline tests** | full suite runs with no network / no keys |

---

## 🔐 Secrets policy (read this)

**Never hardcode API keys** in source, commits, or chat.

| Place | Use |
|-------|-----|
| `.env` (gitignored) | Local bootstrap only — copy from [`.env.example`](.env.example) |
| Encrypted vault | Runtime secrets (Dashboard → Secrets / Connections) |
| Env vars | Optional provider fallbacks (`XAI_API_KEY`, `GROQ_API_KEY`, …) |

```powershell
# After filling .env with YOUR keys (not committed):
uv run python scripts/load_env_to_vault.py   # prints names + lengths only
```

Full policy: [`docs/TOKEN-POLICY.md`](docs/TOKEN-POLICY.md).

---

## 📦 Installation

### 💻 From source (recommended for this fork)

**Prerequisites:** Python 3.12+, [uv](https://docs.astral.sh/uv/), Node 20+ (includes npm), git.

```powershell
git clone https://github.com/Sm0k367/epic-iron-jarvis.git
cd epic-iron-jarvis
uv run ironjarvis doctor          # or: uv run epic doctor
uv sync --extra dev
cd dashboard; npm install; npm run build; cd ..
uv run ironjarvis up             # daemon :8787 + dashboard :3000
```

Two terminals: `uv run ironjarvis serve` + `cd dashboard && npm start`.

Desktop window over source: `cd desktop && npm install && npm start`.

```powershell
uv run ironjarvis demo           # offline end-to-end
uv run pytest -q                 # offline test suite
```

CLI aliases: **`ironjarvis`** and **`epic`** (same app).

### 🪟 Windows desktop installer

Build from this repo:

```powershell
npm --prefix desktop run dist:full
# → desktop/release/… Setup … .exe
```

Published releases (if any) live on this repo’s [Releases](https://github.com/Sm0k367/epic-iron-jarvis/releases). Upstream Iron Jarvis installers may differ in branding.

Closing the window **minimizes to tray** so schedules / webhooks / TG keep running. Quit from the tray menu to fully stop.

### 🧠 One brain across projects

```powershell
# Preferred (Epic Tech AI)
setx EPIC_HOME "$env:USERPROFILE\.epic-tech"
# Still supported
setx IRONJARVIS_HOME "$env:USERPROFILE\.ironjarvis"
```

Unset → per-project `<cwd>/.ironjarvis` isolation.

---

## 🔌 Connect models (few clicks)

**Dashboard → Connections**

| Provider | How |
|----------|-----|
| Anthropic / OpenAI / Google | API key and/or inherited CLI login (`claude` / `codex`) |
| **xAI (Grok)** | API key → vault `xai_api_key` or `XAI_API_KEY` |
| **Groq** | API key → vault `groq_api_key` or `GROQ_API_KEY` |
| OpenRouter | One key, many models |
| Ollama / custom | Base URL in Settings — no key required for local |

CLI:

```powershell
uv run ironjarvis connect xai <paste-key-in-terminal-only>
# Prefer: put key in .env, then load_env_to_vault.py
```

Never put real keys in README, issues, or committed files.

---

## 📱 Telegram bot

| | Recommended |
|--|-------------|
| **Display name** | **Epic Tech AI** |
| **Username** | **`@EpicTechAI_bot`** (or next free `*bot` name on Telegram) |
| **Replies** | Prefixed `Epic Tech AI: ` |

**Full setup:** [`docs/TELEGRAM.md`](docs/TELEGRAM.md) (BotFather → Channels → allowlist).

**Dashboard → Channels** — type `telegram`, bot token, chat id, **Enable two-way = true**, **Allowlist = your user id**.

| Command | Action |
|---------|--------|
| `/help` | List commands |
| `/status` | Version, model, live work |
| `/workflows` · `/run <name>` · `/runs` · `/cancel <id>` | Workflows |
| `/agents` · `/ask <agent> <task>` | Remote agents |
| `/sessions` | Recent sessions |
| `/balance` | Credit balance |
| `/buy [product_id]` | Credit packs / Stripe checkout link |
| `/usage` | Token usage summary |
| *(free text)* | Supervised agent session |

Also: [`docs/REFLEX.md`](docs/REFLEX.md).

---

## 💰 Credits, billing & token budgets

| Piece | Where |
|-------|--------|
| Balance / grant / packs | `GET/POST /billing*` · Dashboard can call the same APIs |
| Stripe Checkout | `POST /billing/checkout` — needs `STRIPE_SECRET_KEY` in env or vault |
| Webhook | `POST /billing/webhook/stripe` |
| Config | `billing_enabled`, `billing_require_credits`, `max_tokens_per_*`, … |

Defaults keep **local free**: billing off; mock/Ollama do not burn credits.

Credit packs (dev catalog): `credits_100` / `credits_500` / `credits_2000` — Stripe Price IDs via `STRIPE_PRICE_CREDITS_*` env vars (never hardcode secret keys).

---

## ☁️ Deploy (optional)

See [`DEPLOY.md`](DEPLOY.md) and `deploy/`. Docker:

```bash
docker compose up
```

Before public exposure: set `IRONJARVIS_TOKEN`, HTTPS, tight CORS, persist state volume, keep computer-use off unless isolated.

---

## 📖 Daily use (short map)

| Surface | What |
|---------|------|
| **Chat / Sessions** | Talk to agents; stop / continue / export |
| **Projects** | Workspace, knowledge, in-project chat |
| **Workflows** | Visual multi-step pipelines |
| **Terminals** | Multi-pane PTY + AI assist |
| **Creative** | Studio + gallery / media |
| **Marketplace** | Connector installs (MCP / OAuth / keys) |
| **Memory / LTM / Lessons** | Recall and self-improvement |
| **Usage** | Tokens & estimated cost |
| **Settings** | Models, autonomy, budgets |
| **Help** | In-app guide |

**Recover:** `doctor` · `repair` · `backup` · `restore` · `rollback` · `reset-config`

> CLI: `init · serve · up · run · demo · cancel · rerun · doctor · repair · backup · restore · connect · secrets · …`

---

## 🏗️ Architecture

```
Dashboard (Next.js)  ──REST + WebSocket──►  Daemon (FastAPI)
                                              │
   Orchestrator · Agents · Tools · Permissions · Sandbox
   Providers (xAI/Groq/…) · Connections vault · Router
   Memory Fabric · LTM · Projects · Creative · Reflex
   Billing ledger · Channels (TG) · Workflows · Schedules
                  SQLite (WAL) under .ironjarvis / EPIC_HOME
```

```
src/iron_jarvis/
  brand.py          Epic Tech AI identity strings
  billing/          credits ledger + Stripe helpers
  daemon/routes/    REST domains (incl. billing)
  reflex/           phone commands + ambient rules
  providers/        LLM adapters (xAI, Groq, …)
  connectors/       marketplace catalog
  projects/ creative/ memory/ comm/ …
dashboard/          Next.js control center
```

---

## 🛡️ Security

- Local-first state; secrets Fernet-encrypted; agents never read secret values.
- Inbound TG: **opt-in**, **allowlist**, private chat only.
- Stripe / provider keys: env or vault only — see TOKEN-POLICY.
- No auto-merge of agent code changes.

---

## 🧪 Verify

```powershell
uv run ironjarvis doctor
uv run ironjarvis demo
uv run python -m pytest tests/test_billing_ledger.py -q
uv run pytest -q
```

---

## 📚 Docs

| Doc | Topic |
|-----|--------|
| [docs/TOKEN-POLICY.md](docs/TOKEN-POLICY.md) | Secrets + token budgets |
| [docs/REFLEX.md](docs/REFLEX.md) | Phone / ambient commands |
| [docs/SIGNING.md](docs/SIGNING.md) | Code-signing the Windows installer |
| [docs/README.md](docs/README.md) | Internal plans & audits |
| [DEPLOY.md](DEPLOY.md) | Server deploy |
| [CLAUDE.md](CLAUDE.md) / [AGENTS.md](AGENTS.md) | Agent operating notes |

## ⚖️ Legal, privacy & whitepages

Full policy pack lives in **[`legal/`](legal/)** and in the dashboard at **`/legal`**.

| Document | Repo | In-app |
|----------|------|--------|
| Privacy Policy | [legal/PRIVACY.md](legal/PRIVACY.md) | `/legal/privacy` |
| Terms of Service | [legal/TERMS.md](legal/TERMS.md) | `/legal/terms` |
| Acceptable Use | [legal/ACCEPTABLE-USE.md](legal/ACCEPTABLE-USE.md) | `/legal/acceptable-use` |
| Billing & Refunds | [legal/BILLING.md](legal/BILLING.md) | `/legal/billing` |
| Cookies & Storage | [legal/COOKIES.md](legal/COOKIES.md) | `/legal/cookies` |
| Security Policy | [SECURITY.md](SECURITY.md) · [legal/SECURITY.md](legal/SECURITY.md) | `/legal/security` |
| Copyright / DMCA | [legal/COPYRIGHT.md](legal/COPYRIGHT.md) | `/legal/copyright` |
| Product Whitepaper | [legal/WHITEPAPER.md](legal/WHITEPAPER.md) | `/legal/whitepaper` |
| Contact | [legal/CONTACT.md](legal/CONTACT.md) | `/legal/contact` |
| License | [LICENSE](LICENSE) | `/legal/license` |
| Third-party notices | [NOTICE](NOTICE) | — |

**Contact:** [epictechai@gmail.com](mailto:epictechai@gmail.com) · [@EpicTechAI](https://x.com/EpicTechAI)

*Policies are for transparency and operations; they are not personalized legal advice.*

---

## 🗺️ Contact & attribution

| | |
|--|--|
| **Product** | Epic Tech AI |
| **Email** | epictechai@gmail.com |
| **X** | [@EpicTechAI](https://x.com/EpicTechAI) |
| **Upstream core** | [Iron Jarvis](https://github.com/RealDealCPA-VR/Iron-Jarvis) by RealDealCPA-VR |

---

<div align="center">

**Epic Tech AI** — *the AI OS you own.*

</div>
