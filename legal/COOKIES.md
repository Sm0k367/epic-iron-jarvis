# Cookie & Local Storage Notice

**Epic Tech AI**  
**Effective date:** July 12, 2026  

Contact: [epictechai@gmail.com](mailto:epictechai@gmail.com)

## 1. Summary

The default **local dashboard** is not an advertising website. It primarily uses **browser local storage** (and similar mechanisms) on **your device** to remember preferences and connect to your local daemon. It does not set third-party ad trackers in the stock build.

## 2. What we use

| Mechanism | Purpose | Required? |
|-----------|---------|-----------|
| `localStorage` | UI prefs (nav mode, layout, model switcher state, etc.) | Functional |
| `localStorage` / session | Optional daemon access token for the dashboard client | Functional when daemon auth is enabled |
| Session storage | Temporary UI state | Functional |
| First-party cookies | May be used by Next.js / hosting if you deploy the dashboard remotely | Depends on deploy |

## 3. Third parties

- If you open **external** links (Stripe Checkout, OAuth providers, documentation sites), those sites may set their own cookies.
- LLM providers are called from the **daemon**, not as browser ad pixels.

## 4. Your controls

- Clear site data in your browser for the dashboard origin
- Use the app offline without connecting remote analytics
- When self-hosting, configure your reverse proxy and cookie flags (Secure, HttpOnly, SameSite) appropriately

## 5. Contact

Questions: [epictechai@gmail.com](mailto:epictechai@gmail.com)
