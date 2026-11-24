"""
Core Bot Logic Handler
Processes Telegram updates (photo, image-document, link, text) and sends formatted HTML responses.
Shared by Local Polling Runner, Webhook Server, and GitHub Actions Single-Shot Worker.
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
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff")

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
    """Sends HTML formatted message to Telegram with 3-attempt retry on transient network drops."""
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    if reply_to_message_id:
        payload["reply_to_message_id"] = reply_to_message_id

    for attempt in range(3):
        try:
            resp = requests.post(f"{API_URL}/sendMessage", json=payload, timeout=15)
            if resp.ok:
                return
            log(f"Telegram sendMessage HTTP {resp.status_code}: {resp.text[:150]}")
        except Exception as e:
            log(f"Telegram reply attempt {attempt + 1} error: {e}")
        if attempt < 2:
            time.sleep(1.5 * (attempt + 1))

def download_telegram_file(file_id: str, dest_path: str) -> bool:
    """Downloads a photo or image document from Telegram servers."""
    try:
        r = requests.get(f"{API_URL}/getFile", params={"file_id": file_id}, timeout=15)
        res = r.json()
        if not res.get("ok"):
            log(f"Telegram getFile failed: {res}")
            return False
        file_path = res["result"]["file_path"]
        download_url = f"{FILE_URL}/{file_path}"

        dl = requests.get(download_url, timeout=30)
        if not dl.ok:
            log(f"Telegram file download HTTP {dl.status_code}")
            return False
        with open(dest_path, "wb") as f:
            f.write(dl.content)
        return True
    except Exception as e:
        log(f"File download error: {e}")
        return False

def _extract_image_file_id(msg: dict, payload: dict) -> str:
    """Extracts highest-res image file_id from Telegram photo, image document, or slimmed payload."""
    if payload.get("photo_file_id"):
        return payload["photo_file_id"]

    photos = msg.get("photo", [])
    if photos:
        return photos[-1].get("file_id", "")

    doc = msg.get("document") or {}
    if doc:
        mime = (doc.get("mime_type") or "").lower()
        fname = (doc.get("file_name") or "").lower()
        if mime.startswith("image/") or fname.endswith(IMAGE_EXTS):
            return doc.get("file_id", "")

    if payload.get("doc_file_id"):
        mime = (payload.get("doc_mime") or "").lower()
        fname = (payload.get("doc_name") or "").lower()
        if mime.startswith("image/") or fname.endswith(IMAGE_EXTS):
            return payload["doc_file_id"]

    return ""

def _format_success_reply(res: dict, footer: str) -> str:
    cv_label = (
        f"<code>{res['cv_attached']}</code> 🌍 (International)"
        if res.get("is_international")
        else f"<code>{res['cv_attached']}</code> 🇮🇳 (India)"
    )
    comp_loc = res.get("company") or "Hiring Team"
    if res.get("location"):
        comp_loc += f" ({res['location']})"
    return f"""🎉 <b>Application Sent Successfully!</b>
━━━━━━━━━━━━━━━━━━━━━━━━━
💼 <b>Role:</b> {res['role']}
🏢 <b>Company:</b> {comp_loc}
📝 <b>Subject:</b> <code>{res['subject']}</code>
✉️ <b>Sent To:</b> <code>{', '.join(res['emails'])}</code>
📎 <b>Attached CV:</b> {cv_label}
━━━━━━━━━━━━━━━━━━━━━━━━━
{footer}"""

def handle_telegram_update(update: dict, runner_footer: str = "🕒 <i>Delivered via Auto Mail Bot</i>"):
    """
    Processes a single incoming Telegram update dict or normalized Cloudflare bridge payload.
    Supports photo flyers, uncompressed image documents, links (including embedded flyer OCR), and raw text.
    """
    if not isinstance(update, dict):
        return
    msg = update.get("message") or update.get("channel_post") or update
    if not isinstance(msg, dict):
        return

    chat_obj = msg.get("chat") if isinstance(msg.get("chat"), dict) else {}
    chat_id = str(chat_obj.get("id") or update.get("chat_id") or AUTHORIZED_CHAT_ID)
    msg_id = msg.get("message_id") or update.get("message_id")
    text = (msg.get("text") or update.get("text") or "").strip()
    caption = (msg.get("caption") or update.get("caption") or "").strip()
    image_file_id = _extract_image_file_id(msg, update)

    if AUTHORIZED_CHAT_ID and chat_id != AUTHORIZED_CHAT_ID:
        log(f"Unauthorized access attempt from Chat ID: {chat_id}")
        return

    if text in ["/start", "/help"]:
        welcome = """👋 <b>Namaste Shuaib!</b>

Aapka <b>Auto-Mail Bot</b> bilkul ready hai! 🚀

Aap jab bhi LinkedIn scroll karein aur koi achhi IT job dikhe:
1️⃣ <b>Post ka Link</b> yahan share/paste kar dein
2️⃣ Ya <b>Post ka Screenshot / Photo</b> yahan bhej dein
3️⃣ Ya <b>Post ka Text copy</b> karke yahan bhej dein

Main turant:
• Flyer / Post Image ka OCR & HR Email extract karunga
• Exact Subject & CV skills match karunga
• Gmail se updated CV attach karke cold email bhej dunga!"""
        send_reply(chat_id, welcome, msg_id)
        return

    # Case 1: Photo / Image Document sent
    if image_file_id:
        send_reply(chat_id, "⚡ <i>Flyer Image detect ho gayi! OCR se HR ki email extract kar rahe hain...</i>", msg_id)
        local_filename = os.path.join(TEMP_DIR, f"tg_{int(time.time())}.jpg")
        try:
            if download_telegram_file(image_file_id, local_filename):
                res = process_and_apply(local_filename, is_image_path=True, extra_text=caption)
                if res.get("success"):
                    send_reply(chat_id, _format_success_reply(res, runner_footer), msg_id)
                else:
                    send_reply(chat_id, f"⚠️ <b>Notice:</b> {res.get('error')}", msg_id)
            else:
                send_reply(chat_id, "❌ Image download karne me dikkat aayi. Kripya dubara try karein.", msg_id)
        finally:
            if os.path.exists(local_filename):
                try:
                    os.remove(local_filename)
                except Exception:
                    pass
        return

    # Case 2: Link or Text sent
    if text or caption:
        input_text = text if not caption else f"{text}\n{caption}".strip()

        if "whatsapp.com/channel" in input_text.lower():
            wa_msg = """⚠️ <b>WhatsApp Channel Link Detect Hua!</b>

WhatsApp Channel ke links browser me direct open nahi hote.
👉 Post ka <b>Text copy</b> karke paste karein ya <b>Screenshot photo</b> bhejein!"""
            send_reply(chat_id, wa_msg, msg_id)
            return

        if "http" in input_text.lower():
            send_reply(chat_id, "🔍 <i>Link detect ho gaya! Post aur flyer images scan karke email bhej rahe hain...</i>", msg_id)
        else:
            send_reply(chat_id, "🔍 <i>Post Text detect ho gaya! Email aur requirements check ho rahi hain...</i>", msg_id)

        res = process_and_apply(input_text, is_image_path=False)
        if res.get("success"):
            send_reply(chat_id, _format_success_reply(res, runner_footer), msg_id)
        elif res.get("is_private"):
            send_reply(chat_id, res.get("error"), msg_id)
        else:
            send_reply(chat_id, f"⚠️ <b>Notice:</b> {res.get('error')}", msg_id)
        return

    log("[Notice]: No actionable text, link, or image found in payload.")
