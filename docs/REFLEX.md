# Reflexes — the Ambient Operator

A **reflex** makes **Epic Tech AI** act on its own: an inbound signal (a webhook
firing, or a message on a comm channel) runs a bound action — a saved workflow,
a remote agent, or a supervised session. A **command grammar** lets you drive the
machine from your phone (Telegram bot display name **Epic Tech AI**, username
e.g. **`@EpicTechAI_bot`** — see [TELEGRAM.md](./TELEGRAM.md)). Everything is
opt-in and runs through the normal permission engine, so a remote signal never
gets more power than you do locally.

Manage it all on the **Reflexes** page (Automate → Reflexes, or `/reflex`). The
Overview's **Ambient operator** card shows how many reflexes are active and their
recent fires.

## The model

A rule binds a **signal** to an **action**:

| Signal (`source`) | Matched on (`match`) |
|---|---|
| `webhook` | the exact inbound webhook **slug** |
| `comm` | a **keyword** (matched as a whole word; blank = every message) |

| Action | Needs (`target`) | Runs |
|---|---|---|
| `workflow` | a saved workflow name | that workflow |
| `remote_agent` | a registered remote-agent name | delegates the task to it |
| `session` | — | a supervised session with the task |

For `session` / `remote_agent`, `task_template` is the task text; the
placeholders `{body}`, `{text}`, and `{slug}` are filled from the triggering
signal. Leave it blank for a sensible default.

## Walkthrough 1 — a webhook that runs a workflow

1. Create the inbound webhook (Automate → **Webhooks**); copy its slug, e.g.
   `deploy`.
2. On **Reflexes**, add a rule: source `webhook`, match `deploy`, action
   `workflow`, target `nightly` (any saved workflow).
3. Click **Test** — it fires immediately and reports the started run id (proving
   the binding without waiting for a real POST).
4. POST to the webhook URL for real; the workflow starts in the background and
   appears under Workflows → Runs. The webhook responds instantly
   (`{"ok": true, "reflexes_fired": 1}`) — it never blocks on the run.

```bash
# once the rule exists, the external system just POSTs the webhook:
curl -X POST "$IRONJARVIS_URL/webhooks/deploy" -H 'content-type: application/json' \
     -d '{"ref":"main"}'
```

## Walkthrough 2 — operate from your phone (command grammar)

Enable inbound on a comm channel (e.g. Telegram) with your sender allowlisted
(Connections → Channels). Then message the bot:

| Command | Does |
|---|---|
| `/status` | version, model, live work |
| `/workflows` | list saved workflows |
| `/run <name>` | start a workflow |
| `/runs` | recent workflow runs |
| `/cancel <run_id>` | stop a running workflow |
| `/agents` | list remote agents |
| `/ask <agent> <task>` | ask a remote agent and get the reply |
| `/sessions` | recent sessions |
| `/balance` | credit balance |
| `/buy [product_id]` | credit packs / Stripe checkout link |
| `/usage` | token usage summary |
| `/help` | this list |

Any message that is **not** a command runs as a normal supervised session (and
replies the summary), exactly as before. Replies are prefixed **`Epic Tech AI:`**.

Full Telegram BotFather setup: **[TELEGRAM.md](./TELEGRAM.md)**.

## Walkthrough 3 — a keyword that triggers work

Add a rule: source `comm`, match `invoice`, action `workflow`, target
`invoice_summary`. Now any allowlisted message containing the whole word
"invoice" fires that workflow instead of a free-form chat, and you get a short
"Triggered: …" confirmation.

## Safety

- **Off by default.** A rule exists only because you created it. Inbound comm is
  off until a channel opts in *and* has credentials; a sender is processed only
  when allowlisted (fail-closed).
- **Normal gates.** Every launched action flows through the orchestrator and the
  permission engine — dangerous tools still require approval.
- **Durable + honest.** Rules persist across restarts; each fire emits a
  `reflex.fired` event and increments the rule's `fire_count` / `last_fired_at`.

## Under the hood

`reflex/` holds the pieces: `ReflexRule` (durable binding), `ReflexStore`
(CRUD + matching), `ReflexRouter` (creates the run-record/session synchronously,
then launches the long part in the background), and `CommandInterpreter` (the
grammar). The inbound webhook handler calls `reflex_router.on_webhook`; the comm
`InboundPoller` dispatches commands, then checks keyword rules via
`on_comm`. HTTP surface: `GET/POST/PATCH/DELETE /reflex/rules` and
`POST /reflex/rules/{id}/test`.

> Note: the declarative `[[triggers]]` TOML block in `workflows/triggers.py` is a
> separate, dormant path (not loaded at boot). The live mechanism is the reflex
> rule store described here.
