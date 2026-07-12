# Privacy Policy

**Epic Tech AI**  
**Effective date:** July 12, 2026  
**Last updated:** July 12, 2026  

Contact: [epictechai@gmail.com](mailto:epictechai@gmail.com) · [@EpicTechAI](https://x.com/EpicTechAI)

## 1. Who we are

Epic Tech AI (“we,” “us,” “our”) builds and distributes **Epic Tech AI**, a local-first AI operating system (the “Software”). This Privacy Policy explains how information is handled when you download, run, or interact with the Software, our documentation, repositories, and any optional cloud or payment features we enable.

## 2. Local-first by design

By default, Epic Tech AI runs **on your own machine**:

- Configuration, SQLite databases, memory, session history, and the encrypted secrets vault typically live under your project’s `.ironjarvis/` directory, `EPIC_HOME`, `IRONJARVIS_HOME`, or the desktop app’s application-data folder.
- We do **not** automatically receive a copy of your local workspace, files, or vault contents merely because you run the Software offline.

You control what leaves your device (for example by connecting cloud LLM providers, Telegram, Stripe, or hosting the daemon on a public server).

## 3. Information you may provide or process

Depending on how you configure the Software, data may include:

| Category | Examples | Where it usually lives |
|----------|----------|------------------------|
| **Account / identity (optional)** | Email if you contact us; Telegram user IDs you allowlist | Your config/vault; our inbox if you email us |
| **Workspace content** | Files agents read/write, chat prompts, project knowledge | Your disk / DB |
| **Secrets** | API keys, bot tokens, OAuth tokens | Encrypted vault on your disk (or env vars you set) |
| **Usage meters** | Token counts, estimated cost, credit ledger | Local DB; optional Stripe if you enable billing |
| **Support correspondence** | Emails you send to epictechai@gmail.com | Our email provider |
| **Repository interaction** | GitHub issues, stars, contributions | GitHub (see GitHub’s privacy policy) |

## 4. Information processed by third parties you connect

If **you** connect external services, those providers process data under **their** policies. Common examples:

- **LLM providers** (Anthropic, OpenAI, Google, xAI, Groq, OpenRouter, etc.) — prompts, tool results, and model outputs you send
- **Stripe** — payment and customer identifiers for credit purchases (we do not store full card numbers)
- **Telegram / Slack / Discord** — messages if you enable channels
- **Hosting** — if you deploy the daemon yourself (Railway, Render, VPS, etc.)

We do not control those processors. Review their policies before enabling integrations.

## 5. How we use information we receive directly

When you contact us or use optional services we operate:

- Respond to support, security, and legal requests
- Improve documentation and product reliability
- Process payments (via Stripe) if you purchase credits or plans we offer
- Enforce Terms, Acceptable Use, and applicable law
- Send operational notices (e.g. security updates) when appropriate

We do **not** sell your personal information.

## 6. Cookies and local storage

The local dashboard may use browser **localStorage** / session storage for UI preferences (theme, nav mode, daemon token on the client, etc.). See [COOKIES.md](./COOKIES.md). We do not use third-party advertising cookies in the default local app.

## 7. Data retention

- **On your machine:** retained until you delete state folders, wipe the vault, or uninstall and remove application data.
- **Email we receive:** retained as needed for support and legal obligations, then deleted or archived under ordinary business practices.
- **Payment records:** retained as required by tax and payment-processor rules (Stripe holds primary payment data).

## 8. Security

See [SECURITY.md](./SECURITY.md) and [docs/TOKEN-POLICY.md](../docs/TOKEN-POLICY.md). Secrets should never be committed to git or pasted into public issues. No method of electronic storage is 100% secure; you are responsible for securing your host, vault keys, and access tokens.

## 9. Children

The Software is not directed to children under 13 (or the minimum age in your jurisdiction). Do not use it to collect children’s personal data unlawfully.

## 10. International users

You are responsible for compliance with laws that apply where you run the Software. If you transfer data to third-country AI or cloud providers, those transfers are under your configuration and their terms.

## 11. Your choices

- Run fully offline with the mock or local Ollama provider
- Disconnect cloud providers and channels at any time
- Delete local state directories and uninstall
- Request deletion of emails you sent us by contacting epictechai@gmail.com (subject to legal holds)

## 12. Changes

We may update this Policy by revising this file and the in-app Legal pages. Material changes will update the “Last updated” date. Continued use after changes constitutes acceptance where permitted by law.

## 13. Contact

**Epic Tech AI**  
Email: [epictechai@gmail.com](mailto:epictechai@gmail.com)  
X: [https://x.com/EpicTechAI](https://x.com/EpicTechAI)
