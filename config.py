"""
Centralized Configuration Module for Auto_mail_bot
Loads environment variables and sets up system constants.
"""

import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMP_DIR = os.path.join(BASE_DIR, "temp_images")
LOG_DIR = os.path.join(BASE_DIR, "logs")
SENT_HISTORY_FILE = os.path.join(BASE_DIR, "sent_history.json")

CV_INDIA_PATH = os.path.join(BASE_DIR, os.environ.get("CV_INDIA_FILENAME", "Shuaib Ali - CV.pdf"))
CV_GLOBAL_PATH = os.path.join(BASE_DIR, os.environ.get("CV_GLOBAL_FILENAME", "Shuaib_Ali.pdf"))
ASK_FREELLM_TOOL = r"C:\Users\IT\Desktop\AGY-Backup\tools\ask_freellm.py"

USER_NAME = os.environ.get("USER_NAME", "Shuaib Ali")
USER_PHONE = os.environ.get("USER_PHONE", "+91 9311534763")
USER_LINKEDIN = os.environ.get("USER_LINKEDIN", "https://www.linkedin.com/in/shuaib-ali-ba0977195")
USER_LOCATION = os.environ.get("USER_LOCATION", "Noida / Delhi NCR, India (Available for Relocation / Remote)")

os.makedirs(TEMP_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

def load_env():
    env_path = os.path.join(BASE_DIR, ".env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip()
                    if k not in os.environ:
                        os.environ[k] = v

load_env()

GMAIL_USER = os.environ.get("GMAIL_USER", "shuaib.ali6347@gmail.com")
GMAIL_PASS = os.environ.get("GMAIL_APP_PASSWORD", "").replace(" ", "")

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
AUTHORIZED_CHAT_ID = str(os.environ.get("TELEGRAM_CHAT_ID", "1229206599"))
LINKEDIN_LI_AT = os.environ.get("LINKEDIN_LI_AT", "").strip()

API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
FILE_URL = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}"

TRACKER_BASE_URL = os.environ.get("TRACKER_BASE_URL", "https://auto-mail-bot-bridge.uto-mail-bot.workers.dev").rstrip("/")
TRACKER_SECRET = os.environ.get("TRACKER_SECRET", "").strip()
