# Epic Tech AI — Product Whitepaper

**Version:** 1.0  
**Date:** July 12, 2026  
**Author:** Epic Tech AI  
**Contact:** epictechai@gmail.com · [@EpicTechAI](https://x.com/EpicTechAI)

## Abstract

Epic Tech AI is a **local-first AI operating system**: a multi-agent runtime, permissioned tool layer, long-term memory, workflow automation, desktop and dashboard UX, and optional commerce (credits). It is designed for operators who want **capability without surrendering control**—every sensitive action is gateable, reviewable, and logged.

The open core draws from the Iron Jarvis architecture (RealDealCPA-VR), extended under the Epic Tech AI brand with multi-provider connectivity (including xAI and Groq), Telegram Reflex commands, and a credits ledger for microtransactions.

## 1. Problem

Cloud chat UIs are easy but opaque. Fully custom agent stacks are powerful but fragile. Users need:

1. **Agency** — models that *do* work (files, tools, workflows), not only chat  
2. **Control** — fail-closed permissions, human review for risky changes  
3. **Privacy defaults** — state on-disk; network optional  
4. **Economics** — clear metering and optional prepaid credits for cloud inference  
5. **Reach** — phone control (Telegram) without opening an unauthenticated RCE surface  

## 2. Solution overview

```
User (Dashboard / Desktop / Telegram)
        │
        ▼
   Daemon (FastAPI) ── Orchestrator ── Agents ── Tools
        │                    │
        ├── Secrets vault (encrypted)
        ├── Memory fabric + LTM
        ├── Workflows / schedules / Reflex
        ├── Projects + Creative Studio
        └── Billing ledger (optional Stripe)
```

### 2.1 Local-first persistence

SQLite (WAL) under `.ironjarvis` / `EPIC_HOME` holds sessions, events, lessons, credits, and configuration. Secrets use Fernet encryption at rest. Agents never read secret *values*—only use them via resolvers.

### 2.2 Multi-agent runtime

A supervisor decomposes goals; specialists run with isolated context. Git-native sessions can land on review-gated worktrees—**no auto-merge**.

### 2.3 Permission engine

Tools are allow / ask / deny. Headless dangerous tools fail closed. Computer-use and shell remain opt-in / gated.

### 2.4 Providers

Connections registry supports API keys and (where applicable) CLI subscription inheritance. Epic Tech AI adds first-class **xAI** and **Groq** alongside Anthropic, OpenAI, Google, OpenRouter, Ollama, and custom OpenAI-compatible endpoints.

### 2.5 Reflex & Telegram

Inbound messages on allowlisted private chats can run deterministic commands (`/status`, `/balance`, `/buy`, …) or spawn supervised sessions. Design goals: **opt-in**, **allowlist**, **private-chat only**.

### 2.6 Commerce

Optional `billing_enabled` master switch. Credit packs via Stripe Checkout; ledger is append-only; mock/Ollama remain free. Secrets never hardcoded—see TOKEN-POLICY.

### 2.7 Connector marketplace

One-tap catalog for MCP / OAuth / API connectors so users expand capability without editing TOML by hand.

## 3. Trust & safety model

| Threat | Mitigation |
|--------|------------|
| Prompt injection → data exfil | Permissions, workspace confinement, human ask modes |
| Stolen host | Disk encryption (OS), vault keys, short-lived tokens |
| Public daemon exposure | Auth token required; docs warn RCE-by-design |
| TG bot takeover | Fail-closed allowlist; non-private chats refused |
| Key leakage in git | `.env` gitignored; secret scan culture; TOKEN-POLICY |

## 4. Data flows (summary)

1. **Offline path:** User → Dashboard → Daemon → Mock/Ollama → local tools only.  
2. **Cloud LLM path:** User → Daemon → Provider API (prompt/tools) → response → local DB.  
3. **Payment path:** User → Stripe Checkout → webhook → local ledger credit.  
4. **Telegram path:** Telegram → long-poll → allowlist → command or session → reply.

## 5. Roadmap themes

- Deeper Settings UX for budgets and legal hub (in-app)
- Optional multi-device sync without sacrificing local defaults  
- Expanded marketplace catalog and audited connector templates  
- Continued hardening and audit surfaces (Activity / undo)

## 6. Compliance posture

We publish Privacy, Terms, AUP, Billing, Cookies, Security, and Copyright policies under `/legal`. Epic Tech AI is local-first; most compliance obligations depend on **how operators deploy** (e.g. GDPR controller vs processor roles when self-hosting for others). Operators should perform their own DPIAs when offering the stack as a multi-tenant service.

## 7. Attribution

Core architecture inspired by and forked from **Iron Jarvis** ([RealDealCPA-VR/Iron-Jarvis](https://github.com/RealDealCPA-VR/Iron-Jarvis)). Epic Tech AI branding, commerce, provider expansions, and documentation: Epic Tech AI.

## 8. Contact

epictechai@gmail.com · https://x.com/EpicTechAI · https://github.com/Sm0k367/epic-iron-jarvis
