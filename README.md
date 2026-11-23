# 🚀 Auto Mail Bot (Universal Job Application & Cold Mailer)

AI-powered on-demand cold email applicant for **Shuaib Ali**.  
Automatically extracts recruiter emails from LinkedIn links, photos, flyers, or text, matches real CV skills, and sends personalized cold emails with the appropriate CV.

---

## 🌟 Dual Mode Architecture (Zero Ban Risk)

1. **Cloud Mode (100% Free on Render - On-Demand Webhook):**
   - Uses `webhook_server.py`.
   - **Zero 24/7 continuous polling loops.**
   - Telegram pushes updates only when you send a message.
   - Script executes in 3-5 seconds and sleeps.

2. **Local Mode (On Your Desktop PC):**
   - Double click `START_LOCAL.bat` or run via Windows Task Scheduler (`run_silent.vbs`).
   - Runs locally without requiring any cloud server.

---

## 📂 Project Structure

```
Auto_mail_bot/
├── config.py              # Environment variables & constants
├── ocr_engine.py          # Windows OCR + PIL contrast enhancement
├── email_sender.py        # Gmail SMTP + dynamic skills & dual CV router
├── apply_engine.py        # Universal parser for link, photo & text
├── bot_core.py            # Core Telegram message & card formatting
├── webhook_server.py      # On-demand Flask webhook server for cloud
├── run_local.py           # Local polling runner for Desktop
├── START_LOCAL.bat        # 1-Click desktop launcher
├── run_silent.vbs         # Silent background runner for Windows Task Scheduler
├── Shuaib Ali - CV.pdf    # Domestic CV (India roles)
├── Shuaib_Ali.pdf         # International CV (Dubai, UAE, Saudi, Europe, etc.)
├── requirements.txt       # Python dependencies
└── Procfile / render.yaml # 1-Click cloud deployment on Render
```

---

## 🎯 Dual CV Auto-Routing

* 🇮🇳 **Domestic (India Roles):** Automatically attaches `Shuaib Ali - CV.pdf`.
* 🌍 **International (UAE, Saudi, Dubai, GCC, Europe, US, UK, etc.):** Automatically attaches `Shuaib_Ali.pdf`.

---

## 🚀 How to Run Locally

Double-click `START_LOCAL.bat` on your Desktop.  
Open Telegram, message `@Shuaib_Job_Mailer_bot`, and send any job link or flyer image!

---

## ☁️ How to Deploy on Render (Cloud Free 24/7)

1. Push this folder to your new GitHub repository.
2. Sign in to [Render.com](https://render.com) and click **New +** -> **Web Service**.
3. Select your repository.
4. Set Environment Variables:
   - `GMAIL_USER`
   - `GMAIL_APP_PASSWORD`
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
5. Click **Deploy**.
6. Set Telegram Webhook (run once in browser):
   ```
   https://api.telegram.org/bot<YOUR_BOT_TOKEN>/setWebhook?url=<YOUR_RENDER_URL>/webhook/<YOUR_BOT_TOKEN>
   ```
