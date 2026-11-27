# 🚀 Auto Mail Bot (Universal Cloud Job Mailer + Free Gmail `✓✓ Read` Tracker)

100% **Serverless, Event-Driven, Zero-Laptop-Dependency** cold email job application bot powered by **Telegram + Cloudflare Workers + GitHub Actions + Gmail**, with a built-in **free email open tracker** that applies a green **`✓✓ Read`** label directly inside your Gmail Sent folder.

> 🤖 **Using an AI IDE (Antigravity / Claude / Cursor) to clone this for someone else?**  
> Just ask the AI to read [AI_SETUP_BLUEPRINT.md](./AI_SETUP_BLUEPRINT.md) and [CLAUDE.md](./CLAUDE.md) — it contains the complete architecture, credential checklist, and 0-to-live deployment runbook.

---

## 🌟 How It Works

1. **Send a Job to Telegram:** Forward a LinkedIn post link, paste job text, or send 1–N flyer screenshots (albums automatically merge into 1 job).
2. **Cloudflare Worker Bridge (`cloudflare_bridge.js`):** Buffers photo albums (`AlbumBuffer` Durable Object) and dispatches instantly to GitHub Actions (`repository_dispatch`).
3. **GitHub Actions Runner (`on_demand_worker.py`):**
   - Extracts HR email, job role, company, location, and explicit subject lines using Playwright + Tesseract OCR.
   - Auto-selects Domestic vs International CV PDF (`email_sender.py`).
   - Sends clean `Plain + HTML` email with CV attached and a tiny `1x1` tracking pixel registered in Cloudflare `MailTracker`.
   - Replies on Telegram with status and shuts down cleanly (0 always-on servers).
4. **Gmail `✓✓ Read` Label (`gmail_read_labeler.gs`):**
   - Ignores delivery-time security scanners & Gmail proxy pre-fetches (`< 60s`), and sends strict `no-store, max-age=0` headers so HR opens **2 minutes, 10 hours, or 30 days later** are still detected accurately.
   - Google Apps Script checks opened emails every 5 minutes and automatically applies the **`✓✓ Read`** label in your Gmail Sent folder (zero Telegram notification spam).

---

## 📂 Key Files

- [AI_SETUP_BLUEPRINT.md](./AI_SETUP_BLUEPRINT.md) — Complete architecture & 0-to-live setup guide for new users & AI assistants
- [CLAUDE.md](./CLAUDE.md) — Quick context file for AI coding IDEs
- [cloudflare_bridge.js](./cloudflare_bridge.js) & [wrangler.toml](./wrangler.toml) — Cloudflare Worker (`AlbumBuffer` + `MailTracker`)
- [email_sender.py](./email_sender.py) & [config.py](./config.py) — Dual CV router, HTML + pixel email builder, Gmail SMTP sender
- [gmail_read_labeler.gs](./gmail_read_labeler.gs) — Free Google Apps Script for Gmail `✓✓ Read` labels
- [apply_engine.py](./apply_engine.py) & [ocr_engine.py](./ocr_engine.py) — Link/OCR/text intelligence engine
- [bot_core.py](./bot_core.py) & [on_demand_worker.py](./on_demand_worker.py) — Telegram & GitHub Actions runner
- [test_suite.py](./test_suite.py) — Unit tests
- [`.github/workflows/on_demand_mailer.yml`](./.github/workflows/on_demand_mailer.yml) — Cloud runner workflow

---

## ⚡ Quick Setup for a New User

See full step-by-step instructions in [AI_SETUP_BLUEPRINT.md](./AI_SETUP_BLUEPRINT.md):
1. Copy/clone repo and replace CV PDFs + update `config.py` / `.env.example` values.
2. Deploy Cloudflare Worker (`npx wrangler deploy` + `npx wrangler secret put GITHUB_TOKEN`).
3. Push to GitHub and configure GitHub Actions Secrets (`GMAIL_USER`, `GMAIL_APP_PASSWORD`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `LINKEDIN_LI_AT`).
4. Set Telegram webhook to your Cloudflare Worker URL.
5. Paste [gmail_read_labeler.gs](./gmail_read_labeler.gs) into [script.google.com](https://script.google.com) under the user's Gmail and run `setupTrigger()` once.
