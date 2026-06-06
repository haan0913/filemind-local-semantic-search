"""
Telegram notification helper for AI_STATION services.
Sends alerts when nightly scans complete or errors occur.
"""
import requests

TELEGRAM_BOT_TOKEN = "env:TELEGRAM_BOT_TOKEN"
CHAT_ID = "env:TELEGRAM_CHAT_ID"

def send_alert(message: str, level: str = "info") -> bool:
    """Send a Telegram message. level: info | warning | error"""
    prefix = {"info": "ℹ️", "warning": "⚠️", "error": "🚨"}.get(level, "ℹ️")
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    resp = requests.post(url, json={"chat_id": CHAT_ID, "text": f"{prefix} {message}"})
    return resp.ok

def notify_scan_complete(files_indexed: int, errors: int) -> None:
    level = "error" if errors > 0 else "info"
    send_alert(f"FileMind scan done. Indexed: {files_indexed}, Errors: {errors}", level)
