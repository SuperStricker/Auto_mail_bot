"""
Local Runner for Auto_mail_bot
Runs on your local PC with safe polling.
Use this when you want to run the bot on your local desktop.
"""

import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# Guard against pythonw.exe NoneType stdout/stderr on Windows
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

import time
import requests
from config import API_URL, TELEGRAM_BOT_TOKEN
from bot_core import handle_telegram_update, log

def run_local():
    log("=" * 60)
    log("🤖 Auto_mail_bot Local Runner Started")
    log("   Listening for Telegram Messages on Local PC...")
    log("=" * 60)

    offset = 0
    while True:
        try:
            params = {"offset": offset, "timeout": 20}
            resp = requests.get(f"{API_URL}/getUpdates", params=params, timeout=25)
            data = resp.json()

            if not data.get("ok"):
                time.sleep(3)
                continue

            for update in data.get("result", []):
                offset = update["update_id"] + 1
                try:
                    handle_telegram_update(update)
                except Exception as e:
                    log(f"Error processing update: {e}")

        except requests.exceptions.Timeout:
            continue
        except requests.exceptions.ConnectionError:
            time.sleep(5)
            continue
        except KeyboardInterrupt:
            log("Local Runner stopped by user.")
            break
        except Exception as e:
            log(f"Unexpected error: {e}")
            time.sleep(3)

if __name__ == "__main__":
    try:
        run_local()
    except Exception as e:
        import traceback
        with open(os.path.join(BASE_DIR, "logs", "fatal_crash.log"), "w", encoding="utf-8") as f:
            traceback.print_exc(file=f)
