"""
Centralized Error Handling + Admin Alerts + File Logging.

Features:
- File-based logging (errors.log) with rotation
- Admin alert via Telegram for critical errors
- User-friendly error classification
- Duplicate message detection
"""

import logging
import os
from datetime import datetime
from logging.handlers import RotatingFileHandler

from src.config import ADMIN_ID

# ═══════════════════════════════════════
# FILE LOGGER SETUP
# ═══════════════════════════════════════

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "errors.log")

error_logger = logging.getLogger("somly_errors")
error_logger.setLevel(logging.ERROR)

# Rotating file handler: max 5MB, keep 3 backups
file_handler = RotatingFileHandler(LOG_FILE, maxBytes=5*1024*1024, backupCount=3, encoding="utf-8")
file_handler.setFormatter(logging.Formatter(
    "[%(asctime)s] [%(levelname)s] %(message)s [user_id=%(user_id)s]",
    datefmt="%Y-%m-%d %H:%M:%S"
))
error_logger.addHandler(file_handler)


# ═══════════════════════════════════════
# ERROR TYPE CONSTANTS
# ═══════════════════════════════════════

class ErrorType:
    GEMINI_RATE_LIMIT = "gemini_rate_limit"
    GEMINI_SERVER = "gemini_server"
    GEMINI_JSON_PARSE = "gemini_json_parse"
    GEMINI_ALL_KEYS_EXHAUSTED = "gemini_all_keys_exhausted"
    MONGODB_CONNECTION = "mongodb_connection"
    MONGODB_DUPLICATE = "mongodb_duplicate"
    MONGODB_GENERAL = "mongodb_general"
    TELEGRAM_BLOCKED = "telegram_blocked"
    TELEGRAM_MESSAGE_TOO_LONG = "telegram_message_too_long"
    TELEGRAM_GENERAL = "telegram_general"
    VOICE_DOWNLOAD = "voice_download"
    VOICE_TOO_SHORT = "voice_too_short"
    VOICE_WHISPER_FAIL = "voice_whisper_fail"
    API_GENERAL = "api_general"
    UNKNOWN = "unknown"


# Critical errors that must alert the admin
CRITICAL_ERRORS = {
    ErrorType.MONGODB_CONNECTION,
    ErrorType.GEMINI_ALL_KEYS_EXHAUSTED,
    ErrorType.GEMINI_SERVER,
}


# ═══════════════════════════════════════
# DUPLICATE DETECTION
# ═══════════════════════════════════════

_recent_messages = {}  # {user_id: (text_hash, timestamp)}
DUPLICATE_WINDOW_SECONDS = 3


def is_duplicate_message(user_id: int, text: str) -> bool:
    """Check if user sent the exact same message within 3 seconds."""
    import hashlib
    text_hash = hashlib.md5(text.encode()).hexdigest()
    now = datetime.now()

    key = f"{user_id}:{text_hash}"
    if key in _recent_messages:
        last_time = _recent_messages[key]
        if (now - last_time).total_seconds() < DUPLICATE_WINDOW_SECONDS:
            return True

    _recent_messages[key] = now

    # Cleanup old entries (keep last 100)
    if len(_recent_messages) > 200:
        sorted_items = sorted(_recent_messages.items(), key=lambda x: x[1], reverse=True)
        _recent_messages.clear()
        _recent_messages.update(dict(sorted_items[:100]))

    return False


# ═══════════════════════════════════════
# LOGGING FUNCTIONS
# ═══════════════════════════════════════

def log_error(error_type: str, message: str, user_id: int = 0, exception: Exception = None):
    """Log error to file with structured format."""
    extra = {"user_id": user_id or "system"}
    full_msg = f"[{error_type}] {message}"
    if exception:
        full_msg += f" | Exception: {type(exception).__name__}: {str(exception)}"
    error_logger.error(full_msg, extra=extra)


async def send_admin_alert(bot, error_type: str, message: str, user_id: int = 0):
    """Send critical error alert to admin via Telegram."""
    if not ADMIN_ID:
        return

    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    alert_text = (
        f"🚨 KRITIK XATO:\n"
        f"Tur: {error_type}\n"
        f"Vaqt: {now}\n"
        f"Xato: {message}\n"
    )
    if user_id:
        alert_text += f"User ID: {user_id}\n"

    try:
        await bot.send_message(int(ADMIN_ID), alert_text)
    except Exception:
        error_logger.error(f"Failed to send admin alert: {alert_text}", extra={"user_id": "system"})


async def handle_error(bot, error_type: str, message: str, user_id: int = 0, exception: Exception = None):
    """
    Central error handler:
    1. Log to file
    2. If critical → alert admin
    """
    log_error(error_type, message, user_id, exception)

    if error_type in CRITICAL_ERRORS and bot:
        await send_admin_alert(bot, error_type, message, user_id)


# ═══════════════════════════════════════
# MESSAGE SPLITTING (4096 char limit)
# ═══════════════════════════════════════

def split_long_message(text: str, max_length: int = 4096) -> list:
    """Split a long message into chunks respecting Telegram's 4096 char limit."""
    if len(text) <= max_length:
        return [text]

    chunks = []
    while text:
        if len(text) <= max_length:
            chunks.append(text)
            break

        # Find the last newline before limit
        split_pos = text.rfind('\n', 0, max_length)
        if split_pos == -1:
            split_pos = max_length

        chunks.append(text[:split_pos])
        text = text[split_pos:].lstrip('\n')

    return chunks


async def safe_send_message(bot, chat_id: int, text: str, **kwargs):
    """Send a message, auto-splitting if too long, handling blocked users and flood wait."""
    from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest, TelegramRetryAfter
    import asyncio

    chunks = split_long_message(text)
    for chunk in chunks:
        try:
            await bot.send_message(chat_id, chunk, **kwargs)
        except TelegramForbiddenError:
            # User blocked the bot
            log_error(ErrorType.TELEGRAM_BLOCKED, f"User {chat_id} blocked the bot", chat_id)
            from src.database import users_collection
            await users_collection.update_one(
                {"telegram_id": chat_id},
                {"$set": {"is_active": False}}
            )
            return False
        except TelegramBadRequest as e:
            err_lower = str(e).lower()
            if "message is too long" in err_lower:
                log_error(ErrorType.TELEGRAM_MESSAGE_TOO_LONG, f"Message too long for {chat_id}", chat_id)
                await bot.send_message(chat_id, chunk[:4000] + "\n\n... (xabar qisqartirildi)", **kwargs)
            elif "chat not found" in err_lower or "user is deactivated" in err_lower:
                log_error(ErrorType.TELEGRAM_BLOCKED, f"Chat not found / deactivated for {chat_id}", chat_id)
                from src.database import users_collection
                await users_collection.update_one(
                    {"telegram_id": chat_id},
                    {"$set": {"is_active": False}}
                )
                return False
            else:
                raise
        except TelegramRetryAfter as e:
            log_error(ErrorType.TELEGRAM_GENERAL, f"Rate limited. Waiting {e.retry_after} seconds", chat_id, e)
            await asyncio.sleep(e.retry_after)
            await bot.send_message(chat_id, chunk, **kwargs)
    return True
