"""
Single-Shot On-Demand Worker for GitHub Actions
Executes ONLY once per event (No while-loop, No continuous cron polling, Exits immediately after finishing).
Triggered by repository_dispatch or workflow_dispatch.
"""

import os
import sys
import json
import time
import argparse
import requests

from config import API_URL
from bot_core import handle_telegram_update

CLOUD_FOOTER = "⚡ <i>GitHub On-Demand Runner (Event-Triggered & exited)</i>"

def process_single_event(payload: dict):
    """Processes a single Telegram event via shared bot_core pipeline."""
    print("=" * 60)
    print("🚀 Auto_mail_bot Single-Shot On-Demand Execution Started")
    print(f"   Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    handle_telegram_update(payload, runner_footer=CLOUD_FOOTER)

def poll_and_process_pending():
    """On-demand utility to drain any previously queued Telegram updates."""
    print("=" * 60)
    print("🔍 Checking Telegram Queue for Pending Messages...")
    print(f"   Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    try:
        r = requests.get(f"{API_URL}/getUpdates", timeout=15)
        data = r.json()
        if not data.get("ok"):
            print(f"[Error]: Telegram getUpdates failed: {data}")
            return

        updates = data.get("result", [])
        if not updates:
            print("✅ No pending updates found in Telegram queue. Exiting gracefully.")
            return

        print(f"⚡ Found {len(updates)} pending update(s). Processing now...")
        for u in updates:
            up_id = u["update_id"]
            print(f"\n--- Processing Update ID: {up_id} ---")
            try:
                process_single_event(u)
            except Exception as e:
                print(f"[Update Error on {up_id}]: {e}")
            try:
                requests.get(f"{API_URL}/getUpdates", params={"offset": up_id + 1}, timeout=10)
            except Exception as e:
                print(f"[Offset Error]: {e}")

        print("\n✅ All pending Telegram updates processed and queue cleared!")
    except Exception as e:
        print(f"[Polling Error]: {e}")

def parse_cli_or_env_payload(raw_payload: str, raw_text: str) -> dict | None:
    """Resolves clean payload dict from JSON string or text, ignoring GitHub 'null'/'{}' values."""
    cleaned = (raw_payload or "").strip()
    if cleaned and cleaned not in ("null", "None", "{}"):
        try:
            loaded = json.loads(cleaned)
            if isinstance(loaded, dict) and loaded:
                return loaded
        except Exception:
            return {"text": cleaned}
    if (raw_text or "").strip():
        return {"text": raw_text.strip()}
    return None

def main():
    parser = argparse.ArgumentParser(description="Run single on-demand job application")
    parser.add_argument("--payload", type=str, default="", help="JSON payload from Telegram / GitHub Event")
    parser.add_argument("--text", type=str, default="", help="Direct text/link input")
    parser.add_argument("--poll", action="store_true", help="Drain queued Telegram getUpdates once")
    args = parser.parse_args()

    raw_payload = args.payload or os.environ.get("PAYLOAD_JSON", "")
    raw_text = args.text or os.environ.get("JOB_TEXT_OR_URL", "")
    payload = parse_cli_or_env_payload(raw_payload, raw_text)

    if args.poll:
        poll_and_process_pending()
    elif payload:
        process_single_event(payload)
    else:
        poll_and_process_pending()

    print("✅ Execution complete. Exiting gracefully with code 0.")
    sys.exit(0)

if __name__ == "__main__":
    main()
