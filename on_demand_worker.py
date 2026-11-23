"""
Single-Shot On-Demand Worker for GitHub Actions
Executes ONLY once per event (No while-loop, No polling, Exits immediately in ~15-30s).
Triggered by repository_dispatch or workflow_dispatch.
"""

import os
import sys
import json
import time
import argparse
import requests

from config import (
    API_URL, FILE_URL, TELEGRAM_BOT_TOKEN, AUTHORIZED_CHAT_ID, TEMP_DIR
)
from apply_engine import process_and_apply

def send_reply(chat_id: str, text: str, reply_to_message_id: int = None):
    """Sends HTML formatted reply back to Telegram."""
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
        print(f"[Telegram Reply Error]: {e}")

def download_telegram_file(file_id: str, dest_path: str) -> bool:
    """Downloads a photo from Telegram servers."""
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
        print(f"[File Download Error]: {e}")
        return False

def process_single_event(payload: dict):
    """
    Processes a single Telegram event and immediately terminates.
    Payload can come from:
      1. Cloudflare bridge / repository_dispatch: contains raw Telegram message dict
      2. Manual workflow_dispatch: contains {"text": "..."} or {"image_url": "..."}
    """
    print("=" * 60)
    print("🚀 Auto_mail_bot Single-Shot On-Demand Execution Started")
    print(f"   Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # 1. Extract message structure
    msg = payload.get("message") or payload
    chat_id = str(msg.get("chat", {}).get("id") or payload.get("chat_id") or AUTHORIZED_CHAT_ID)
    msg_id = msg.get("message_id")
    text = (msg.get("text") or payload.get("text") or "").strip()
    caption = (msg.get("caption") or payload.get("caption") or "").strip()
    photos = msg.get("photo", [])

    # Security check: authorize only user's chat_id if configured
    if AUTHORIZED_CHAT_ID and chat_id != AUTHORIZED_CHAT_ID:
        print(f"[Blocked]: Unauthorized chat_id {chat_id}")
        return

    # Handle /start or /help
    if text in ["/start", "/help"]:
        welcome = """👋 <b>Namaste Shuaib!</b>

Aapka <b>GitHub On-Demand Mailer</b> active hai! ⚡
Yeh bot 24/7 nahi chalta—sirf tab jaagta hai jab aap photo ya link bhejte ho!

Abhi koi bhi:
1️⃣ <b>Job Flyer / Screenshot Photo</b> bhejein
2️⃣ <b>LinkedIn Post Link</b> bhejein
3️⃣ <b>Job Description Text</b> bhejein

Main turant 30 seconds mein email bhej kar band ho jaunga!"""
        send_reply(chat_id, welcome, msg_id)
        return

    # Case 1: Photo / Screenshot / Flyer sent
    if photos:
        send_reply(chat_id, "⚡ <i>GitHub Action jaag gaya! Flyer ka OCR aur email process ho raha hai...</i>", msg_id)
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
⚡ <i>GitHub On-Demand Runner (Ran for ~25s & exited)</i>"""
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

WhatsApp Channel ke links browser me open nahi hote.
👉 Post ka <b>Text copy</b> karke bhejein ya <b>Screenshot photo</b> bhejein!"""
            send_reply(chat_id, wa_msg, msg_id)
            return

        send_reply(chat_id, "⚡ <i>GitHub Action jaag gaya! Details analyze karke email bhej rahe hain...</i>", msg_id)
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
⚡ <i>GitHub On-Demand Runner (Ran for ~20s & exited)</i>"""
            send_reply(chat_id, reply, msg_id)
        else:
            send_reply(chat_id, f"⚠️ <b>Notice:</b> {res.get('error')}", msg_id)
        return

    print("[Notice]: No actionable text or photo found in payload.")

def main():
    parser = argparse.ArgumentParser(description="Run single on-demand job application")
    parser.add_argument("--payload", type=str, default="", help="JSON payload from Telegram / GitHub Event")
    parser.add_argument("--text", type=str, default="", help="Direct text/link input")
    args = parser.parse_args()

    payload = {}
    if args.payload:
        try:
            payload = json.loads(args.payload)
        except Exception:
            payload = {"text": args.payload}
    elif args.text:
        payload = {"text": args.text}

    process_single_event(payload)
    print("✅ Single execution complete. Exiting gracefully with code 0.")
    sys.exit(0)

if __name__ == "__main__":
    main()
