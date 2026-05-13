import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is missing in .env")

ADMIN_ID = os.getenv("ADMIN_ID")

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DB_NAME = os.getenv("DB_NAME", "somly_ai")

_keys = os.getenv("GROQ_API_KEYS", "")
_raw_keys = [k.strip().strip('"').strip("'") for k in _keys.split(",") if k.strip()]
# Filter out obviously invalid keys
GROQ_API_KEYS = [k for k in _raw_keys if len(k) > 20 and k.startswith("gsk_")]
_skipped = len(_raw_keys) - len(GROQ_API_KEYS)
if _skipped > 0:
    print(f"[CONFIG] WARNING: {_skipped} invalid API key(s) skipped (must start with 'gsk_' and be >20 chars)")
if not GROQ_API_KEYS:
    raise ValueError("GROQ_API_KEYS is missing or all keys are invalid")

GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
