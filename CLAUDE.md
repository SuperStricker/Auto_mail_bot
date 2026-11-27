# Auto_mail_bot — AI IDE Auto-Context (`CLAUDE.md`)

> **READ THIS FIRST (For Any AI Coding Assistant / IDE):**  
> This repository is a **100% Cloud-Serverless, Event-Driven Cold Mail Bot + Free Gmail Read-Receipt (`✓✓ Read` Label) System**.  
> **NEVER** start local background polling bots (`run_local.py`) or rely on local-only runs unless explicitly asked — everything runs live on **Cloudflare Workers + GitHub Actions + Google Apps Script**.

## Quick Orientation
- **Full 0-to-Live Replication & Onboarding Blueprint:** Read [AI_SETUP_BLUEPRINT.md](./AI_SETUP_BLUEPRINT.md) before making changes or cloning this setup for a new user.
- **How to Replicate for a New User:** Ask the new user ONLY for the credentials/assets listed in Section 2 of `AI_SETUP_BLUEPRINT.md`, then follow Section 4 step-by-step to deploy their own isolated GitHub Repo + Cloudflare Worker + Telegram Webhook + Gmail `✓✓ Read` Apps Script from scratch and verify live on GitHub Actions.

## Key Files
| File | Role |
|------|------|
| `cloudflare_bridge.js` + `wrangler.toml` | Cloudflare Worker: `AlbumBuffer` (Telegram photo/album batching -> GitHub `repository_dispatch`) + `MailTracker` (1x1 GIF open pixel, 60s anti-prefetch filter, SQLite DO storage) |
| `on_demand_worker.py` + `.github/workflows/on_demand_mailer.yml` | Single-shot GitHub Actions cloud runner (exits cleanly after 1 job) |
| `bot_core.py` + `apply_engine.py` + `ocr_engine.py` | Extracts HR email, job title, company, location from LinkedIn links, multi-screenshot flyers (OCR), or raw text |
| `email_sender.py` + `config.py` | Dual CV router (India vs International), builds `multipart/alternative` (plain + HTML with `1x1` pixel), sends via Gmail SMTP, registers `track_id` on Cloudflare `MailTracker` |
| `gmail_read_labeler.gs` | Runs inside the user's Gmail account via Google Apps Script (`setupTrigger()` -> every 5 min) and applies the `✓✓ Read` label to opened Sent emails |
| `test_suite.py` | Automated unit test suite (run after every edit before pushing) |

## Engineering Rules
1. Always run `python test_suite.py` before pushing.
2. Whenever `cloudflare_bridge.js` or `wrangler.toml` changes, immediately run `npx wrangler deploy` AND push to `GitHub`.
3. Never commit `.env` or real secrets (`GMAIL_APP_PASSWORD`, `TELEGRAM_BOT_TOKEN`, `LINKEDIN_LI_AT`, `GITHUB_TOKEN`).
