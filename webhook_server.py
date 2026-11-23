"""
On-Demand Webhook Server (FastAPI / Flask)
Used for 100% Free Cloud Deployment on Render / Railway / Cloudflare.
Only executes when Telegram pushes an update — Zero Continuous Polling, Zero Ban Risk!
"""

import os
from flask import Flask, request, jsonify
from config import TELEGRAM_BOT_TOKEN
from bot_core import handle_telegram_update, log

app = Flask(__name__)

@app.route("/", methods=["GET"])
@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint for Uptime monitoring / Render keep-alive."""
    return jsonify({
        "status": "online",
        "service": "Auto Mail Bot Webhook Server",
        "mode": "on-demand"
    }), 200

@app.route(f"/webhook/{TELEGRAM_BOT_TOKEN}", methods=["POST"])
def telegram_webhook():
    """Webhook endpoint where Telegram sends messages automatically."""
    update = request.get_json(silent=True)
    if not update:
        return "Invalid JSON", 400

    try:
        handle_telegram_update(update)
    except Exception as e:
        log(f"Error handling update: {e}")

    return "OK", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    log(f"Starting On-Demand Webhook Server on port {port}...")
    app.run(host="0.0.0.0", port=port)
