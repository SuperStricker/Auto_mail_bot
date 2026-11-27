# Auto_mail_bot — Complete Architecture & 0-to-Live Replication Blueprint

> **Purpose of This Document:**  
> Any AI assistant (Antigravity, Claude Code, Cursor, etc.) or developer reading this folder can understand the **entire system end-to-end** and **build + deploy an identical live setup from zero for a brand-new user**, simply by collecting the new user's IDs/credentials below and executing the deployment steps.

---

## 1. End-to-End Architecture (100% Free, Serverless, Zero Laptop Dependency)

```text
[1] User sends Job Link / Text / Multi-Screenshot Flyer to Telegram Bot
        │
        ▼  (Telegram Webhook HTTPS POST)
[2] Cloudflare Worker (cloudflare_bridge.js) — `AlbumBuffer` Durable Object
        │  • Buffers multi-image albums for 3 seconds so Top+Bottom screenshots merge into 1 job
        │  • Text/Links dispatch immediately
        │  • Triggers GitHub `repository_dispatch` (`event_type: "telegram_job"`)
        ▼
[3] GitHub Actions (.github/workflows/on_demand_mailer.yml) — Ubuntu Runner
        │  • Runs `on_demand_worker.py` -> `bot_core.py` -> `apply_engine.py`
        │  • Extracts HR email, job role, company, location (Playwright + Tesseract OCR)
        │  • Selects Domestic vs International CV PDF
        │  • `email_sender.py` sends multipart email (Plain + HTML + 1x1 pixel + CV PDF) via Gmail SMTP
        │  • Calls `POST <WORKER_URL>/track/register` with `{ track_id, to_email, subject, sent_at }`
        │  • Sends confirmation card back to Telegram and exits (0 persistent background processes)
        ▼
[4] Recipient (HR) Opens Email (2 min, 10 hours, or 30 days later)
        │  • Email client requests `<img src="<WORKER_URL>/t?id=<track_id>">`
        │  • Cloudflare `MailTracker` Durable Object (SQLite):
        │      - Ignores hits < 60 seconds after `sent_at` (blocks delivery scanners & Gmail Image Proxy pre-fetch)
        │      - Returns 43-byte 1x1 GIF with strict `Cache-Control: no-store, no-cache, must-revalidate, max-age=0`
        │        so Gmail Image Proxy does NOT serve stale cached pixels 10+ hours later
        │      - Marks `opened = 1` for real opens >= 60s (stored up to 90 days)
        ▼
[5] Google Apps Script (gmail_read_labeler.gs) inside User's Gmail Account
        │  • Runs automatically every 5 minutes (100% free, zero GCP billing)
        │  • Calls `GET <WORKER_URL>/track/opened`
        │  • Finds matching thread in `in:sent to:<to_email>`, applies Gmail label `✓✓ Read`
        │  • Calls `POST <WORKER_URL>/track/mark-labeled`
        ▼
[6] User sees green `✓✓ Read` tag directly inside Gmail Sent folder (ZERO Telegram spam!)
```

---

## 2. Checklist: What to Collect from a New User Before Building

Ask the new user for these items (guide them on where to get each):

| # | Item Required | How the New User Gets It | Where It Goes |
|---|---|---|---|
| 1 | **Gmail Address** (`GMAIL_USER`) | Their Gmail ID (e.g., `name@gmail.com`) | GitHub Secret + `.env` |
| 2 | **Gmail App Password (16 chars)** (`GMAIL_APP_PASSWORD`) | Google Account -> Security -> 2-Step Verification (ON) -> App Passwords -> Generate for "Mail" | GitHub Secret + `.env` |
| 3 | **Telegram Bot Token** (`TELEGRAM_BOT_TOKEN`) | Telegram `@BotFather` -> `/newbot` -> copy HTTP API token | GitHub Secret + `.env` |
| 4 | **Telegram Chat ID** (`TELEGRAM_CHAT_ID`) | Message `@userinfobot` on Telegram -> copy numeric ID | GitHub Secret + `.env` |
| 5 | **GitHub Account + PAT** (`GITHUB_TOKEN`) | New repo (e.g. `username/Auto_mail_bot`); Fine-grained or Classic PAT with `repo` & `workflow` scopes | Cloudflare Worker Secret (`wrangler secret put GITHUB_TOKEN`) |
| 6 | **Cloudflare Account** | Free Cloudflare account (`dash.cloudflare.com`), authenticate CLI with `npx wrangler login` | Hosts `cloudflare_bridge.js` |
| 7 | **CV PDFs (1 or 2)** | Domestic CV (e.g. `Name - CV.pdf`) and optional International CV (e.g. `Name_Global.pdf`) | Root of repo |
| 8 | **Profile / Signature Info** | Full Name, Phone, LinkedIn URL, Location/Availability, and Target Job Titles (for `apply_engine.py` & `email_sender.py`) | `config.py` / GitHub Vars / `apply_engine.py` |
| 9 | **LinkedIn `li_at` Cookie** *(Optional)* | Chrome DevTools -> Application -> Cookies -> `linkedin.com` -> `li_at` | GitHub Secret `LINKEDIN_LI_AT` |
| 10 | **Tracker Secret** *(Optional)* | Any random passphrase (recommended if deploying for others so `/track/opened` is private) | Cloudflare Secret + GitHub Secret + `gmail_read_labeler.gs` |

---

## 3. Files to Customize for a New User

When cloning this folder for a new user:
1. **Replace CV PDFs** in repo root (e.g., `NewUser - CV.pdf` and `NewUser_Global.pdf`).
2. **Update `config.py` (or set env vars / GitHub Secrets):**
   - `USER_NAME`, `USER_PHONE`, `USER_LINKEDIN`, `USER_LOCATION`
   - `CV_INDIA_FILENAME`, `CV_GLOBAL_FILENAME`
   - `TRACKER_BASE_URL` (update to the new user's deployed `https://<worker>.workers.dev` URL)
   - `TRACKER_SECRET` (if configured)
3. **Update `email_sender.py`:**
   - Update `CV_SKILLS_MAP` (lines 20–45) and the 1-line intro in `create_email_body()` (`With over X years of experience across ...`) to match the new user's actual background and CVs!
4. **Update `apply_engine.py`:**
   - Update `USER_HEADLINE_PATTERNS` (line 51+) and geo/role defaults to match the new user's target job titles.
5. **Update `wrangler.toml` & `cloudflare_bridge.js`:**
   - Set `GITHUB_REPO = "<new_github_user>/<new_repo>"` in `wrangler.toml` (and fallback in `cloudflare_bridge.js` line 183).
   - Give the worker a unique `name` in `wrangler.toml` (e.g., `name = "auto-mail-bot-<username>"`).
6. **Update `gmail_read_labeler.gs`:**
   - Set `TRACKER_BASE_URL` to the new user's deployed Cloudflare Worker URL (and `TRACKER_SECRET` if used).

---

## 4. Step-by-Step Build & Live Deployment Runbook (0 to Live)

Execute these exact steps in order:

### Step 1: Prepare Local Copy & Verify Tests
```bash
git clone <source-or-new-repo>
# Place new user's CV PDFs, customize config.py / email_sender.py / apply_engine.py / wrangler.toml
python test_suite.py
```

### Step 2: Deploy Cloudflare Worker (`AlbumBuffer` + `MailTracker`)
```bash
npx wrangler login
npx wrangler deploy
# Note the deployed URL: https://<worker-name>.<subdomain>.workers.dev
npx wrangler secret put GITHUB_TOKEN
# (Optional) npx wrangler secret put TRACKER_SECRET
```
- Update `TRACKER_BASE_URL` in `config.py` and `gmail_read_labeler.gs` to the deployed worker URL.
- Verify live worker: `GET https://<worker-url>/` must return `200` (`LIVE & ACTIVE!`).
- Verify live pixel: `GET https://<worker-url>/t?id=test` (with browser User-Agent) must return `200 image/gif` (43 bytes) with `Cache-Control: no-store, no-cache, must-revalidate, max-age=0`.

### Step 3: Push Code & Set GitHub Repository Secrets
```bash
git add .
git commit -m "Configure Auto_mail_bot for <New User>"
git push origin main
```
Set GitHub Actions Secrets (`gh secret set` or Repo -> Settings -> Secrets and variables -> Actions):
- `GMAIL_USER`
- `GMAIL_APP_PASSWORD`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `LINKEDIN_LI_AT` *(optional)*
- `TRACKER_SECRET` *(if set in Step 2)*

### Step 4: Connect Telegram Bot to Cloudflare Worker (Webhook)
Open in browser or curl once:
```text
https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/setWebhook?url=https://<worker-url>/
```
Verify webhook info:
```text
https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/getWebhookInfo
```

### Step 5: Set Up Free Gmail `✓✓ Read` Labeler (Inside New User's Gmail)
1. Log into [script.google.com](https://script.google.com) with the new user's Gmail (`GMAIL_USER`).
2. Click **New project**, delete placeholder code, and paste `gmail_read_labeler.gs` (with their `TRACKER_BASE_URL` & `TRACKER_SECRET`).
3. Click **Save**, select function **`setupTrigger`** in the toolbar dropdown, and click **Run**.
4. Grant Gmail + external request permissions on the Google consent prompt (Advanced -> Go to project -> Allow).
5. Done! Every 5 minutes `syncOpenedEmailsToGmailLabels()` checks Cloudflare and adds **`✓✓ Read`** to opened Sent emails.
6. *(Optional UI Tip)* In Gmail left sidebar under Labels, click the 3 dots on `✓✓ Read` -> Label color -> **Green** so it looks just like WhatsApp/Mailtrack ticks.

### Step 6: Mandatory Live Cloud Verification (Never Local-Only)
1. **Trigger GitHub Actions live test:**
   ```bash
   gh api repos/<user>/<repo>/dispatches --input - <<< '{"event_type":"telegram_job","client_payload":{"chat_id":"<TELEGRAM_CHAT_ID>","text":"Hiring IT Support Engineer in Noida, India. Send CV to <test-inbox@gmail.com>"}}'
   ```
2. **Watch run complete:** `gh run watch --exit-status` -> verify Telegram confirmation message & email arrival in `<test-inbox>`.
3. **Verify Anti-Prefetch + 10-Hour Open Tracking:**
   - Do **NOT** preview your own Sent email in Gmail right after sending (or wait > 60s when testing from the recipient inbox).
   - Verify delivery-time proxy hits (`< 60s` after `sent_at`) do NOT trigger `/track/opened`.
   - Verify hits `>= 60s` (or 10 hours later!) register `opened = 1` in `/track/opened` and get labeled **`✓✓ Read`** on the next 5-minute Apps Script run.

---

## 5. Known Nuances & Best Practices (Read Before Troubleshooting)
- **Why 60-Second Anti-Prefetch Window?** Gmail's `GoogleImageProxy` and corporate mail security scanners routinely pre-fetch embedded images 10–50 seconds after delivery. Ignoring `< 60s` prevents false double-ticks on delivery while keeping real opens (`2 min`, `10 hr`, `30 days` later) accurate.
- **Why Strict `no-store, max-age=0` Headers?** Without `max-age=0` + `CDN-Cache-Control: no-store`, `GoogleImageProxy` or Cloudflare CDN caches the delivery-time scan and never re-fetches 10 hours later when HR opens the email.
- **Do Not Preview Your Own Sent Email Immediately:** Opening your own Sent email in Gmail after 60 seconds loads images from your own session. View the Sent list subject/badges instead; let the recipient trigger the pixel!
- **Cloudflare Bot Fight / `User-Agent`:** Python `urllib` default `User-Agent` can get HTTP 403 from Cloudflare edge; always send a custom `User-Agent` (already handled in `email_sender.py` as `AutoMailBot/1.0`).
- **Privacy & Security:** `.env`, `sent_history.json` (if sensitive), and secret tokens must NEVER be committed to GitHub.
