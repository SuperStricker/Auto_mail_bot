"""
Core Bot Logic Handler
Processes Telegram updates (photo, link, text) and sends formatted HTML responses.
Shared by both Webhook Server and Local Polling Runner.
"""

import os
import sys
import time
import requests
from datetime import datetime

from config import (
    API_URL, FILE_URL, TELEGRAM_BOT_TOKEN, AUTHORIZED_CHAT_ID, TEMP_DIR, LOG_DIR
)
from apply_engine import process_and_apply

LOG_FILE = os.path.join(LOG_DIR, "bot.log")

def log(msg: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted = f"[{timestamp}] {msg}"
    if sys.stdout is not None:
        try:
            print(formatted, flush=True)
        except Exception:
            pass
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(formatted + "\n")
            f.flush()
    except Exception:
        pass

def send_reply(chat_id: str, text: str, reply_to_message_id: int = None):
    """Sends HTML formatted message to Telegram."""
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    if reply_to_message_id:
        payload["reply_to_message_id"] = reply_to_message_id
    try:
        requests.post(f"{API_URL}/sendMessage", json=payload, timeout=15)
    except Exception as e:
        log(f"Failed to send Telegram message: {e}")

def download_telegram_file(file_id: str, dest_path: str) -> bool:
    """Downloads a photo or document from Telegram servers."""
    try:
        r = requests.get(f"{API_URL}/getFile", params={"file_id": file_id}, timeout=15)
        res = r.json()
        if not res.get("ok"):
            return False
        file_path = res["result"]["file_path"]
        download_url = f"{FILE_URL}/{file_path}"

        dl = requests.get(download_url, timeout=30)
        with open(dest_path, "wb") as f:
            f.write(dl.content)
        return True
    except Exception as e:
        log(f"File download error: {e}")
        return False

def handle_telegram_update(update: dict):
    """Processes a single incoming Telegram update dict."""
    msg = update.get("message") or update.get("channel_post")
    if not msg:
        return

    chat_id = str(msg.get("chat", {}).get("id"))
    msg_id = msg.get("message_id")
    text = (msg.get("text") or "").strip()
    caption = (msg.get("caption") or "").strip()
    photos = msg.get("photo", [])

    # Security check: authorize only user's chat_id if configured
    if AUTHORIZED_CHAT_ID and chat_id != AUTHORIZED_CHAT_ID:
        log(f"Unauthorized access attempt from Chat ID: {chat_id}")
        return

    # Command: /start or /help
    if text in ["/start", "/help"]:
        welcome = """👋 <b>Namaste Shuaib!</b>

Aapka <b>Auto-Mail Bot</b> bilkul ready hai! 🚀

Aap jab bhi LinkedIn scroll karein aur koi achhi IT job dikhe:
1️⃣ <b>Post ka Link</b> yahan share/paste kar dein
2️⃣ Ya <b>Post ka Screenshot / Photo</b> yahan bhej dein
3️⃣ Ya <b>Post ka Text copy</b> karke yahan bhej dein

Main turant:
• Flyer ka OCR & Recruiter Email extract karunga
• Exact Subject & CV skills match karunga
• Gmail se updated CV attach karke cold email bhej dunga!

<i>Abhi koi bhi LinkedIn link ya photo bhej kar test karein!</i>"""
        send_reply(chat_id, welcome, msg_id)
        return

    # Case 1: Photo / Flyer sent
    if photos:
        send_reply(chat_id, "🔍 <i>Flyer Image detect ho gayi! OCR se HR ki email extract kar rahe hain...</i>", msg_id)
        highest_photo = photos[-1]
        file_id = highest_photo["file_id"]
        local_filename = os.path.join(TEMP_DIR, f"tg_{int(time.time())}.jpg")

        if download_telegram_file(file_id, local_filename):
            res = process_and_apply(local_filename, is_image_path=True)
            if res.get("success"):
                cv_label = f"<code>{res['cv_attached']}</code> 🌍 (International)" if res.get('is_international') else f"<code>{res['cv_attached']}</code> 🇮🇳 (India)"
                comp_loc = res['company'] or "Hiring Team"
                if res.get('location'):
                    comp_loc += f" ({res['location']})"
                reply = f"""🎉 <b>Application Sent Successfully!</b>
━━━━━━━━━━━━━━━━━━━━━━━━━
💼 <b>Role:</b> {res['role']}
🏢 <b>Company:</b> {comp_loc}
📝 <b>Subject:</b> <code>{res['subject']}</code>
✉️ <b>Sent To:</b> <code>{', '.join(res['emails'])}</code>
📎 <b>Attached CV:</b> {cv_label}
━━━━━━━━━━━━━━━━━━━━━━━━━
🕒 <i>Delivered via Auto Mail Bot</i>"""
                send_reply(chat_id, reply, msg_id)
            else:
                send_reply(chat_id, f"⚠️ <b>Notice:</b> {res.get('error')}", msg_id)
        else:
            send_reply(chat_id, "❌ Image download karne me dikkat aayi. Kripya dubara try karein.", msg_id)
        return

    # Case 2: Link or Text sent
    if text or caption:
        input_text = text if not caption else f"{text}\n{caption}"

        if "whatsapp.com/channel" in input_text.lower():
            wa_msg = """⚠️ <b>WhatsApp Channel Link Detect Hua!</b>

WhatsApp Channel ke links browser me direct open nahi hote.
👉 Post ka <b>Text copy</b> karke paste karein ya <b>Screenshot photo</b> bhejein!"""
            send_reply(chat_id, wa_msg, msg_id)
            return

        if "http" in input_text.lower():
            send_reply(chat_id, "🔍 <i>Link detect ho gaya! Details analyze karke email bhej rahe hain...</i>", msg_id)
        else:
            send_reply(chat_id, "🔍 <i>Post Text detect ho gaya! Email aur requirements check ho rahi hain...</i>", msg_id)

        res = process_and_apply(input_text, is_image_path=False)
        if res.get("success"):
            cv_label = f"<code>{res['cv_attached']}</code> 🌍 (International)" if res.get('is_international') else f"<code>{res['cv_attached']}</code> 🇮🇳 (India)"
            comp_loc = res['company'] or "Hiring Team"
            if res.get('location'):
                comp_loc += f" ({res['location']})"
            reply = f"""🎉 <b>Application Sent Successfully!</b>
━━━━━━━━━━━━━━━━━━━━━━━━━
💼 <b>Role:</b> {res['role']}
🏢 <b>Company:</b> {comp_loc}
📝 <b>Subject:</b> <code>{res['subject']}</code>
✉️ <b>Sent To:</b> <code>{', '.join(res['emails'])}</code>
📎 <b>Attached CV:</b> {cv_label}
━━━━━━━━━━━━━━━━━━━━━━━━━
🕒 <i>Delivered via Auto Mail Bot</i>"""
            send_reply(chat_id, reply, msg_id)
        else:
            send_reply(chat_id, f"⚠️ <b>Notice:</b> {res.get('error')}", msg_id)
