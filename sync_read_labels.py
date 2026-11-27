"""
Gmail Read Labels Synchronizer
Fetches newly opened emails from Cloudflare MailTracker and applies the '✓✓ Read' label
directly to the corresponding sent emails in Gmail via IMAP.
Runs on GitHub Actions (triggered on mail_opened or periodic schedule) or locally.
"""

import sys
import json
import imaplib
import urllib.request
from config import GMAIL_USER, GMAIL_PASS, TRACKER_BASE_URL, TRACKER_SECRET

# Modified UTF-7 representation for "✓✓ Read" in IMAP
LABEL_UTF7 = "&JxMnEw- Read"

def fetch_opened_emails():
    """Fetches opened but unlabeled emails from Cloudflare Worker."""
    if not TRACKER_BASE_URL:
        print("[Sync] No TRACKER_BASE_URL configured.")
        return []
    
    url = f"{TRACKER_BASE_URL}/track/opened"
    if TRACKER_SECRET:
        url += f"?secret={urllib.parse.quote(TRACKER_SECRET)}"
    
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "AutoMailBot-LabelSync/1.0"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            return data.get("items", [])
    except Exception as e:
        print(f"[Sync] Error fetching opened emails: {e}")
        return []

def mark_emails_labeled(track_ids):
    """Notifies Cloudflare Worker that these emails have been labeled in Gmail."""
    if not track_ids or not TRACKER_BASE_URL:
        return
    url = f"{TRACKER_BASE_URL}/track/mark-labeled"
    if TRACKER_SECRET:
        url += f"?secret={urllib.parse.quote(TRACKER_SECRET)}"
    
    payload = json.dumps({"track_ids": track_ids}).encode('utf-8')
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "AutoMailBot-LabelSync/1.0"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            pass
    except Exception as e:
        print(f"[Sync] Error marking emails labeled: {e}")

def sync_read_labels():
    items = fetch_opened_emails()
    if not items:
        print("[Sync] No pending opened emails to label.")
        return 0

    print(f"[Sync] Found {len(items)} opened email(s) waiting for Gmail label.")
    
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(GMAIL_USER, GMAIL_PASS)
        mail.select('"[Gmail]/Sent Mail"')
    except Exception as e:
        print(f"[Sync] IMAP connection failed: {e}")
        return 0

    labeled_ids = []
    
    for item in items:
        to_email = (item.get("to_email") or "").strip()
        target_subject = (item.get("subject") or "").strip().lower()
        track_id = item.get("track_id")
        
        if not to_email:
            continue
            
        print(f"[Sync] Searching Sent Mail for TO: {to_email}")
        try:
            typ, data = mail.search(None, "TO", f'"{to_email}"')
            msg_ids = data[0].split()
            if not msg_ids:
                print(f"[Sync] No sent emails found for {to_email}")
                continue
                
            matched_msg = None
            # Check latest messages first
            for mid in reversed(msg_ids[-10:]):
                typ, fetch_res = mail.fetch(mid, '(BODY[HEADER.FIELDS (SUBJECT)])')
                for r in fetch_res:
                    if isinstance(r, tuple):
                        hdr_text = r[1].decode('utf-8', errors='ignore').lower()
                        if not target_subject or target_subject in hdr_text:
                            matched_msg = mid
                            break
                if matched_msg:
                    break
            
            # If no exact subject match, use the most recent email to this recipient
            target_mid = matched_msg or msg_ids[-1]
            res, _ = mail.store(target_mid, '+X-GM-LABELS', f'("{LABEL_UTF7}")')
            if res == "OK":
                print(f"[Sync] Applied '✓✓ Read' label to email to {to_email} (Msg ID: {target_mid})")
                labeled_ids.append(track_id)
            else:
                print(f"[Sync] Failed to apply label: {res}")
        except Exception as e:
            print(f"[Sync] Error processing item {item}: {e}")

    try:
        mail.logout()
    except Exception:
        pass

    if labeled_ids:
        mark_emails_labeled(labeled_ids)
        print(f"[Sync] Successfully labeled {len(labeled_ids)} email(s).")
        
    return len(labeled_ids)

if __name__ == "__main__":
    sync_read_labels()
