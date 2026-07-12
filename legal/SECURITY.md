# Security Policy

**Epic Tech AI**  
**Effective date:** July 12, 2026  

Contact for vulnerabilities: [epictechai@gmail.com](mailto:epictechai@gmail.com)  
Subject line: `SECURITY`

Also published at repository root: [../SECURITY.md](../SECURITY.md)

## 1. Supported versions

We accept security reports against the **latest `master`** branch of [epic-iron-jarvis](https://github.com/Sm0k367/epic-iron-jarvis). Older tags may not receive backports.

## 2. Design assumptions

- The daemon is a **powerful local agent runtime**. Misconfigured network exposure can allow remote code execution by design.
- Secrets belong in the **encrypted vault** or environment variables — never in git.
- Telegram inbound control is **fail-closed** (allowlist + opt-in). Misconfiguration is an operator risk.

## 3. Reporting a vulnerability

Please email **epictechai@gmail.com** with:

- Description and impact
- Steps to reproduce (PoC)
- Affected commit / version if known
- Whether you plan public disclosure and preferred timeline

**Do not** open a public GitHub issue for unpatched critical vulnerabilities.

We aim to acknowledge within **72 hours** and provide a status update within **7 days**.

## 4. Safe harbor

We will not pursue legal action against researchers who:

- Act in good faith
- Avoid privacy violations, data destruction, and service disruption beyond what’s needed to demonstrate the issue
- Give us reasonable time to fix before public disclosure
- Do not exploit the issue for profit or harm third parties

## 5. Out of scope (examples)

- Issues solely in third-party LLM or Stripe services
- Social engineering of end users
- Reports without a plausible exploit path
- Secrets you leaked yourself in public chat (please rotate and do not resend)

## 6. Hardening checklist (operators)

- [ ] Never expose `:8787` without `IRONJARVIS_TOKEN` (or equivalent) and TLS
- [ ] Keep computer-use and shell permissions restrictive unless intentionally elevated
- [ ] Telegram: inbound only for allowlisted private senders
- [ ] Rotate keys after any suspected exposure
- [ ] Run `ironjarvis doctor` / review Activity audit for anomalies
- [ ] Follow [docs/TOKEN-POLICY.md](../docs/TOKEN-POLICY.md)

## 7. Preferred languages

English.
