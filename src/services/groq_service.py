"""
Groq AI Service with API key rotation.

Features:
- Multiple API keys rotation on 429 / quota / connection errors
- 30s cooldown when all keys exhausted
- Transaction parsing with enhanced 7-step analysis
- Whisper audio transcription
- Name extraction from voice
- Comprehensive error classification for user-friendly messages
"""

import json
import os
import logging
import asyncio
import time
import aiohttp
from datetime import datetime
from typing import List, Dict, Any
from dataclasses import dataclass
from groq import AsyncGroq, APIStatusError, APITimeoutError, APIConnectionError
from src.config import GROQ_API_KEYS, GROQ_MODEL, ADMIN_ID, BOT_TOKEN
from src.categories import get_all_category_names_for_ai
from src.services.error_handler import (
    log_error, ErrorType
)

logger = logging.getLogger(__name__)

# Groq request limits per user: {user_id: [ts1, ts2, ...]}
groq_user_requests = {}
GROQ_USER_LIMIT_1M = 20

def check_groq_limit(user_id: int) -> bool:
    """Returns True if allowed, False if exceeded limit."""
    if not user_id:
        return True
    now = time.time()
    if user_id not in groq_user_requests:
        groq_user_requests[user_id] = []
    
    # Clean old requests (> 60s)
    groq_user_requests[user_id] = [ts for ts in groq_user_requests[user_id] if now - ts <= 60]
    
    if len(groq_user_requests[user_id]) >= GROQ_USER_LIMIT_1M:
        return False
        
    groq_user_requests[user_id].append(now)
    return True


class GroqQueueError(Exception):
    """Raised when all API keys are exhausted or cooling, and request must be queued."""
    pass


class GroqServerError(Exception):
    """Groq returned 500+ server error."""
    pass


class WhisperInvalidAudioError(Exception):
    """
    Audio file rejected by Groq's Whisper model (bad format, too large, corrupted).
    NOTE: Transkripsiya OpenAI Whisper API orqali emas, Groq orqali bajariladi.
    Groq o'z serverlarida `whisper-large-v3` va `whisper-large-v3-turbo` modellarini host qiladi.
    """
    pass


class WhisperAllKeysExhaustedError(Exception):
    """
    All Groq API keys returned 401/quota — none can transcribe audio.
    Bu OpenAI bilan bog'liq emas — barcha kalitlar Groq kalitlari.
    """
    pass


@dataclass
class KeyStats:
    key: str
    index: int
    client: AsyncGroq
    status: str = "active" # "active", "cooling", "exhausted"
    requests_count: int = 0
    last_error_time: float = 0.0
    connection_errors: int = 0
    admin_alerted: bool = False  # True if admin already received alert for this key being disabled


# ═══════════════════════════════════════
# MODEL FALLBACK CHAIN
# ═══════════════════════════════════════
# Groq tashkilot darajasidagi TPD (Tokens Per Day) limit haqida:
#   - llama-3.3-70b-versatile: 100,000 TPD (juda kichik!)
#   - llama-3.1-8b-instant:    500,000+ TPD (5x ko'p), tezroq, arzonroq
#   - llama-3.3-70b-instant:   musbat hollarda quality ham yaxshi
#
# Asosiy model 429 (rate limit) qaytarsa, ROUTING avtomatik kichik modelga o'tadi
# va kunlik reset bo'lguncha (00:00 UTC) shu kichikda qoladi.
MODEL_FALLBACK_CHAIN = [
    # Tier 1: foydalanuvchi tanlagan (.env'dan)
    # Tier 2: 70B kichik versiya — quality o'xshash, limit yumshoq
    "llama-3.3-70b-versatile",
    # Tier 3: 8B — har doim ishlaydi, 5x token limit
    "llama-3.1-8b-instant",
]


def _next_fallback_model(current: str) -> str:
    """Joriy modeldan keyingi (kichikroq) modelni qaytaradi."""
    # Agar joriy modelni topa olsak, undan keyingisini ber
    try:
        # GROQ_MODEL chain'da bo'lmasa, uni boshiga qo'shamiz
        chain = list(MODEL_FALLBACK_CHAIN)
        if current and current not in chain:
            chain.insert(0, current)
        idx = chain.index(current)
        if idx + 1 < len(chain):
            return chain[idx + 1]
    except (ValueError, AttributeError):
        pass
    return "llama-3.1-8b-instant"  # Final fallback har doim 8B


class GroqService:
    def __init__(self):
        self.keys_stats = []
        for i, key in enumerate(GROQ_API_KEYS):
            self.keys_stats.append(KeyStats(
                key=key,
                index=i,
                client=AsyncGroq(api_key=key, timeout=15.0)
            ))
        logger.info(f"GroqService initialized with {len(self.keys_stats)} API key(s)")

        # ─── Active model tracker (avtomatik fallback uchun) ───
        # Boshlang'ich .env'dan, lekin 429 bo'lsa fallback chain'ga o'tadi
        self.active_model = GROQ_MODEL
        self.original_model = GROQ_MODEL  # kelajakda reset uchun
        self.model_demoted_date = None     # qaysi kunda demotion qilingan (UTC ISO date)
        self.tpd_estimate = 0              # taxminiy kunlik token ishlatish (faqat statistika uchun)
        self.tpd_reset_date = None         # ISO date — TPD oxirgi reset bo'lgan kun

    def _maybe_reset_daily(self):
        """UTC kun o'zgargan bo'lsa model va TPD'ni reset qilamiz."""
        import datetime as _dt
        today = _dt.datetime.utcnow().date().isoformat()
        if self.tpd_reset_date != today:
            self.tpd_reset_date = today
            self.tpd_estimate = 0
            # Modelni asliga qaytaramiz (yangi kun, yangi limit)
            if self.active_model != self.original_model:
                logger.info(f"Daily reset: model {self.active_model} → {self.original_model}")
                self.active_model = self.original_model
                self.model_demoted_date = None

    def _demote_model(self, reason: str):
        """429 sabab modelni keyingi (kichikroq) fallback'ga o'tkazamiz."""
        import datetime as _dt
        new_model = _next_fallback_model(self.active_model)
        if new_model == self.active_model:
            logger.warning(f"Model already at smallest fallback ({self.active_model}); no further demotion.")
            return
        old = self.active_model
        self.active_model = new_model
        self.model_demoted_date = _dt.datetime.utcnow().date().isoformat()
        logger.warning(f"MODEL DEMOTION: {old} → {new_model} (reason: {reason})")
        asyncio.create_task(self.alert_admin(
            f"⚠️ Groq model auto-fallback: {old} → {new_model}\nSabab: {reason}\nKun boshida ({self.original_model}) ga qaytadi."
        ))

    async def validate_keys_on_startup(self):
        """Test each key with a minimal API call at startup. Mark invalid ones immediately.

        Validatsiya uchun 8B-instant ishlatamiz (har doim mavjud, kichik limit yeydi).
        Asosiy model bilan tekshirish 70B limit'ini yegan bo'lardi.

        401 kalitlar XOTIRADAN BUTUNLAY OLIB TASHLANADI — rotation orqali
        ham qaytib urinilmaydi (yaroqsiz kalit yana 401 berishi aniq).
        """
        # Tashkilot ID'larini yig'amiz — agar barcha kalitlar bir xil org'da bo'lsa, alert
        org_ids_seen = set()

        for ks in self.keys_stats:
            try:
                response = await ks.client.chat.completions.create(
                    messages=[{"role": "user", "content": "hi"}],
                    model="llama-3.1-8b-instant",  # validation uchun har doim 8B
                    max_tokens=5,
                )
                logger.info(f"Key {ks.index+1}: VALID")
            except APIStatusError as e:
                status_code = getattr(e, 'status_code', 0)
                err_low = str(e).lower()
                if status_code == 401:
                    ks.status = "exhausted"
                    ks.admin_alerted = True  # alert spam'ini oldini olamiz
                    ks.last_error_time = time.time()
                    logger.warning(f"Key {ks.index+1}: INVALID (401) — disabled permanently")
                elif status_code == 429:
                    # Rate limited but key is valid
                    logger.info(f"Key {ks.index+1}: VALID (rate limited, will cool down)")
                    # Org ID xatoda ko'rinishi mumkin (org_01...)
                    import re
                    m = re.search(r"org_[a-z0-9]+", err_low)
                    if m:
                        org_ids_seen.add(m.group(0))
                else:
                    logger.warning(f"Key {ks.index+1}: Error {status_code} during validation")
            except Exception as e:
                logger.warning(f"Key {ks.index+1}: Validation error — {str(e)[:100]}")

        # ── 401 kalitlarni xotiradan butunlay olib tashlaymiz ──
        before = len(self.keys_stats)
        self.keys_stats = [k for k in self.keys_stats if k.status != "exhausted"]
        # Index'larni qayta raqamlash (loglar tushunarli bo'lsin)
        for new_idx, k in enumerate(self.keys_stats):
            k.index = new_idx
        removed = before - len(self.keys_stats)
        if removed > 0:
            logger.info(f"Removed {removed} invalid key(s) from rotation. {len(self.keys_stats)} active key(s) remain.")

        active = sum(1 for ks in self.keys_stats if ks.status == "active")
        logger.info(f"Key validation complete: {active}/{len(self.keys_stats)} active")
        if active == 0 and len(self.keys_stats) == 0:
            logger.error("WARNING: No valid API keys! All requests will fail.")
            await self.alert_admin("🚨 BARCHA Groq API kalitlari yaroqsiz! .env faylidagi GROQ_API_KEYS ni yangilang.")

        # ── Tashkilot diversifikatsiyasi haqida ogohlantirish ──
        # Agar 429 xatolarda bir xil org_id ko'rinsa, alert
        if len(org_ids_seen) == 1 and len(self.keys_stats) > 1:
            org_id = list(org_ids_seen)[0]
            logger.warning(
                f"All keys appear to be from single org ({org_id}). "
                f"Groq TPD limits are PER-ORG — rotation won't help. "
                f"Recommend adding keys from a different Groq account."
            )

    async def alert_admin(self, message: str):
        try:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
            async with aiohttp.ClientSession() as session:
                await session.post(url, json={"chat_id": ADMIN_ID, "text": message})
        except Exception as e:
            logger.error(f"Failed to send admin alert: {e}")

    def get_best_key(self) -> KeyStats:
        """
        Eng yaxshi mavjud kalitni qaytaradi.
        - cooling kalitlar 60s o'tgan bo'lsa darhol aktivga aylanadi
        - hech qanday aktiv kalit yo'q bo'lsa, ENG ESKI cooling kalitni FORCE qaytaramiz
          (foydalanuvchini cheksiz kutkazmaslik uchun, oxirgi chora sifatida)
        - hamma kalit 401/quota bo'lsa GroqServerError
        """
        now = time.time()

        # 1. Cooling → active, agar 60s o'tgan bo'lsa
        for ks in self.keys_stats:
            if ks.status == "cooling" and (now - ks.last_error_time) > 60:
                ks.status = "active"
                ks.connection_errors = 0
                logger.info(f"Groq API Key {ks.index+1} reactivated after cooling.")

        # 2. Aktiv kalit bor — eng kam ishlatilganini olamiz
        active_keys = [ks for ks in self.keys_stats if ks.status == "active"]
        if active_keys:
            return min(active_keys, key=lambda x: x.requests_count)

        # 3. Aktiv yo'q. Tekshiramiz: hammasi 401 bo'lsami?
        exhausted_keys = [ks for ks in self.keys_stats if ks.status == "exhausted"]
        if len(exhausted_keys) == len(self.keys_stats):
            raise GroqServerError("All API keys are permanently exhausted (401/Quota).")

        # 4. Faqat cooling kalitlar qoldi — ENG ESKI sovugani FORCE aktivga aylantiramiz
        # (foydalanuvchini cheksiz "Bir daqiqa..." kutkazmaslik uchun)
        cooling_keys = [ks for ks in self.keys_stats if ks.status == "cooling"]
        if cooling_keys:
            oldest = max(cooling_keys, key=lambda x: (now - x.last_error_time))
            wait_s = now - oldest.last_error_time
            if wait_s > 10:  # kamida 10s sovugan bo'lsa, sinab ko'ramiz
                oldest.status = "active"
                oldest.connection_errors = 0
                logger.warning(f"Force-promoting cooling Key {oldest.index+1} after {wait_s:.1f}s (no active keys available)")
                return oldest

        raise GroqQueueError("All keys are exhausted or cooling. Queueing required.")

    async def chat_completion_with_retry(self, messages: List[Dict], **kwargs) -> str:
        # Kun o'zgargan bo'lsa active_model'ni original'ga qaytaramiz
        self._maybe_reset_daily()

        attempts = 0
        max_retries = len(self.keys_stats) * 2
        model_for_this_call = self.active_model
        # 413 bo'lsa — messages'ni qisqartirib qayta urinamiz (1 marta)
        payload_already_stripped = False

        while attempts < max_retries:
            try:
                ks = self.get_best_key()
            except GroqQueueError:
                raise  # immediately propagate so handler can queue

            try:
                response = await ks.client.chat.completions.create(
                    messages=messages,
                    model=model_for_this_call,
                    **kwargs
                )
                ks.requests_count += 1
                ks.connection_errors = 0
                # TPD taxminiy hisoblash
                try:
                    used = getattr(response, 'usage', None)
                    if used and hasattr(used, 'total_tokens'):
                        self.tpd_estimate += used.total_tokens
                except Exception:
                    pass
                return response.choices[0].message.content
            except APIStatusError as e:
                status_code = getattr(e, 'status_code', 0)
                error_str = str(e)
                err_low = error_str.lower()
                logger.error(f"Groq API Error (key {ks.index+1}, model={model_for_this_call}, status={status_code}): {error_str[:200]}")

                # ── 413 Payload Too Large: chat_history'ni tashlab qayta urinamiz ──
                # KALIT AYBDOR EMAS — cooling QILMAYMIZ, model demote QILMAYMIZ.
                if status_code == 413 or "payload too large" in err_low or "context_length" in err_low:
                    if not payload_already_stripped and len(messages) > 2:
                        # System + last user xabar qoldiramiz, oradagi chat_history'ni o'chiramiz
                        system_msgs = [m for m in messages if m.get("role") == "system"]
                        last_user = next(
                            (m for m in reversed(messages) if m.get("role") == "user"),
                            None,
                        )
                        messages = system_msgs + ([last_user] if last_user else [])
                        payload_already_stripped = True
                        logger.warning(f"413 payload — chat_history dropped, retrying with {len(messages)} messages")
                        attempts += 1
                        continue
                    # Allaqachon strip qilingan, hali 413 — bu prompt yoki kontekst muammosi
                    raise GroqServerError(f"413 Payload Too Large even after history strip: {error_str[:120]}")

                if status_code == 429 or "rate" in err_low or status_code == 403:
                    org_tpd_hit = (
                        "tokens per day" in err_low
                        or "tpd" in err_low
                        or "daily" in err_low
                        or "organization" in err_low
                    )
                    if org_tpd_hit:
                        # Avval modelni demote qilib darrov qayta urinamiz
                        if model_for_this_call == self.active_model:
                            self._demote_model(f"429 TPD hit: {error_str[:120]}")
                            model_for_this_call = self.active_model
                            attempts += 1
                            continue
                        # Demote ham qilingan bo'lsa-yu hali ham TPD — kalit kun oxirigacha exhausted
                        # (Cheksiz cooling/reactivate loop'ni oldini olamiz)
                        ks.status = "exhausted"
                        ks.last_error_time = time.time() + 86400  # 24h — kun oxirigacha
                        log_error(ErrorType.GROQ_RATE_LIMIT, f"Key {ks.index+1} TPD-exhausted (until day reset)", exception=e)
                        if not ks.admin_alerted:
                            ks.admin_alerted = True
                            asyncio.create_task(self.alert_admin(
                                f"🚨 Key {ks.index+1} kunlik TPD limit yegan. Kun oxirigacha o'chirilgan."
                            ))
                    else:
                        # Odatdagi RPM rate-limit — kalitni cooling
                        ks.status = "cooling"
                        ks.last_error_time = time.time()
                        log_error(ErrorType.GROQ_RATE_LIMIT, f"Key {ks.index+1} rate limited (cooling)", exception=e)
                elif status_code == 401 or "invalid_api_key" in error_str.lower():
                    ks.status = "exhausted"
                    ks.last_error_time = time.time()
                    log_error(ErrorType.GROQ_RATE_LIMIT, f"Key {ks.index+1} invalid (401)", exception=e)
                    if not ks.admin_alerted:
                        ks.admin_alerted = True
                        asyncio.create_task(self.alert_admin(f"🚨 Groq API Key {ks.index+1} is INVALID (401 Unauthorized). It has been disabled."))
                elif "quota" in error_str.lower():
                    ks.status = "exhausted"
                    ks.last_error_time = time.time()
                    log_error(ErrorType.GROQ_RATE_LIMIT, f"Key {ks.index+1} quota exceeded", exception=e)
                    if not ks.admin_alerted:
                        ks.admin_alerted = True
                        asyncio.create_task(self.alert_admin(f"🚨 Groq API Key {ks.index+1} EXHAUSTED (Quota exceeded)."))
                elif status_code >= 500:
                    raise GroqServerError(f"Groq server error: {status_code}")
                else:
                    raise e
            except (APITimeoutError, APIConnectionError) as e:
                logger.error(f"Groq connection error (key {ks.index+1}): {str(e)}")
                ks.connection_errors += 1
                if ks.connection_errors >= 3:
                    ks.status = "cooling"
                    ks.last_error_time = time.time()
                    logger.warning(f"Key {ks.index+1} connection errors maxed. Cooling down.")

            attempts += 1

        raise GroqQueueError("All API keys exhausted after max retries")

    async def stream_chat_completion_with_retry(self, messages: List[Dict], **kwargs):
        attempts = 0
        max_retries = len(self.keys_stats) * 2

        while attempts < max_retries:
            try:
                ks = self.get_best_key()
            except GroqQueueError:
                yield "Xatolik: Barcha API kalitlar band yoki limit tugagan."
                return

            try:
                stream = await ks.client.chat.completions.create(
                    messages=messages,
                    model=self.active_model,  # fallback chain'dan joriy modelni olamiz
                    stream=True,
                    **kwargs
                )
                async for chunk in stream:
                    if chunk.choices and chunk.choices[0].delta.content:
                        yield chunk.choices[0].delta.content
                ks.requests_count += 1
                ks.connection_errors = 0
                return
            except APIStatusError as e:
                status_code = getattr(e, 'status_code', 0)
                error_str = str(e)
                logger.error(f"Groq Stream Error (key {ks.index+1}): {error_str}")

                if status_code == 429 or "rate" in error_str.lower() or status_code == 403:
                    ks.status = "cooling"
                    ks.last_error_time = time.time()
                elif status_code == 401 or "invalid_api_key" in error_str.lower():
                    ks.status = "exhausted"
                    ks.last_error_time = time.time()
                elif "quota" in error_str.lower():
                    ks.status = "exhausted"
                    ks.last_error_time = time.time()
                elif status_code >= 500:
                    pass
            except (APITimeoutError, APIConnectionError) as e:
                ks.connection_errors += 1
                if ks.connection_errors >= 3:
                    ks.status = "cooling"
                    ks.last_error_time = time.time()
                
            attempts += 1
            await asyncio.sleep(1) # wait before retry
        
        yield "Xatolik: Tizim hozircha javob bera olmaydi (max retries)."

    async def transcribe_audio_with_retry(self, file_path: str) -> str:
        """
        Audio faylni Groq orqali transkribe qiladi.

        MUHIM: Bu OpenAI Whisper API emas — Groq'ning audio endpointidan foydalanamiz.
        - SDK: `AsyncGroq` (groq paketi), `ks.client.audio.transcriptions.create(...)`
        - Server: api.groq.com (NOT api.openai.com)
        - Modellar: `whisper-large-v3-turbo` va `whisper-large-v3` — Groq'da host qilingan
        - Autentifikatsiya: GROQ_API_KEYS (`.env`)

        Key rotation + model fallback bilan ishlaydi.

        Raises:
            WhisperInvalidAudioError: fayl rad etildi (format/o'lcham/buzilgan)
            WhisperAllKeysExhaustedError: barcha Groq kalitlar 401/quota
            GroqServerError: Groq 500+ qaytardi
            GroqQueueError: kalitlar sovuyapti, so'rov navbatga qo'yilishi kerak
        """
        file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0
        fname = os.path.basename(file_path)
        logger.info(f"Groq Whisper start: file={fname}, size={file_size} bytes")

        # Groq tomonidan host qilingan Whisper modellari (turbo birinchi — 2x tezroq)
        models_to_try = ["whisper-large-v3-turbo", "whisper-large-v3"]
        # Try each key with each model: 2 models × N keys attempts
        max_retries = len(self.keys_stats) * len(models_to_try)
        attempts = 0
        invalid_audio_count = 0  # 400/413/415 across attempts

        while attempts < max_retries:
            try:
                ks = self.get_best_key()
            except GroqQueueError:
                # No active keys — check if all are exhausted (401/quota) vs cooling
                exhausted = sum(1 for k in self.keys_stats if k.status == "exhausted")
                if exhausted == len(self.keys_stats):
                    raise WhisperAllKeysExhaustedError("All Groq API keys are invalid/quota-exceeded")
                raise

            # Alternate model per attempt — every key sees both models
            model = models_to_try[attempts % len(models_to_try)]

            try:
                with open(file_path, "rb") as file:
                    file_data = file.read()

                transcription = await ks.client.audio.transcriptions.create(
                    file=(fname, file_data),
                    model=model,
                    response_format="json",
                )
                ks.requests_count += 1
                ks.connection_errors = 0
                text = transcription.text or ""
                logger.info(f"Groq Whisper success (model={model}, key={ks.index+1}, size={file_size}): {text[:80]}...")
                return text
            except APIStatusError as e:
                status_code = getattr(e, 'status_code', 0)
                error_str = str(e)
                logger.error(f"Groq Whisper error (key={ks.index+1}, model={model}, status={status_code}, size={file_size}): {error_str[:200]}")

                if status_code == 429 or "rate" in error_str.lower() or status_code == 403:
                    ks.status = "cooling"
                    ks.last_error_time = time.time()
                elif status_code == 401 or "invalid_api_key" in error_str.lower():
                    ks.status = "exhausted"
                    ks.last_error_time = time.time()
                    if not ks.admin_alerted:
                        ks.admin_alerted = True
                        asyncio.create_task(self.alert_admin(f"🚨 Groq API Key {ks.index+1} is INVALID (401) for Audio. Disabled."))
                elif "quota" in error_str.lower():
                    ks.status = "exhausted"
                    ks.last_error_time = time.time()
                    if not ks.admin_alerted:
                        ks.admin_alerted = True
                        asyncio.create_task(self.alert_admin(f"🚨 Groq API Key {ks.index+1} EXHAUSTED (Audio Quota)."))
                elif status_code in (400, 413, 415, 422):
                    # File-level error — won't be fixed by switching keys
                    invalid_audio_count += 1
                    if invalid_audio_count >= 2:
                        # Confirmed across 2 attempts → it's the file, not the key
                        raise WhisperInvalidAudioError(f"Audio rejected by Groq Whisper: status={status_code}, {error_str[:120]}")
                elif status_code >= 500:
                    raise GroqServerError(f"Groq server error: {status_code}")
                else:
                    # Unknown status — log loudly, try next attempt
                    logger.warning(f"Groq Whisper unknown status {status_code} on key {ks.index+1}, will retry")
            except (APITimeoutError, APIConnectionError) as e:
                logger.error(f"Groq Whisper connection error (key={ks.index+1}): {str(e)[:150]}")
                ks.connection_errors += 1
                if ks.connection_errors >= 3:
                    ks.status = "cooling"
                    ks.last_error_time = time.time()
            except FileNotFoundError:
                logger.error(f"Groq Whisper: audio file not found: {file_path}")
                raise WhisperInvalidAudioError(f"Audio file missing: {file_path}")
            except Exception as e:
                # Unexpected — log and try next attempt
                logger.error(f"Groq Whisper unexpected error (key={ks.index+1}, model={model}): {type(e).__name__}: {str(e)[:150]}")

            attempts += 1

        # All retries exhausted — check final state
        exhausted = sum(1 for k in self.keys_stats if k.status == "exhausted")
        if exhausted == len(self.keys_stats):
            raise WhisperAllKeysExhaustedError("All Groq API keys are invalid/quota-exceeded")
        raise GroqQueueError("All API keys exhausted for audio after retries")

    # ═══════════════════════════════════════
    # ISMNI AJRATIB OLISH (ovozdan)
    # ═══════════════════════════════════════
    async def extract_name(self, transcribed_text: str) -> str:
        """Ovozdan kelgan matndan faqat ismni ajratib oladi."""
        messages = [
            {"role": "system", "content": (
                "Foydalanuvchi o'z ismini aytdi. Matndan FAQAT ismni ajratib ber. "
                "Agar 'Mening ismim Xusniddin' desa → 'Xusniddin' deb qaytar. "
                "Agar faqat 'Sardor' desa → 'Sardor' deb qaytar. "
                "Hech qanday qo'shimcha so'z, izoh yoki belgi qo'shma. "
                "Faqat ism yozilsin, boshqa hech narsa bo'lmasin."
            )},
            {"role": "user", "content": transcribed_text}
        ]
        try:
            result = await self.chat_completion_with_retry(
                messages, temperature=0.0, max_tokens=50
            )
            # Clean up
            return result.strip().strip('"').strip("'").strip(".")
        except Exception:
            return transcribed_text.strip()

    # ═══════════════════════════════════════
    # JINSNI ANIQLASH (AI orqali)
    # ═══════════════════════════════════════
    async def detect_gender(self, name: str) -> str:
        """
        Ism orqali jinsni aniqlaydi.
        Qaytaradi: 'male', 'female', yoki 'unknown'
        """
        if not name or len(name) < 2:
            return "unknown"
            
        messages = [
            {"role": "system", "content": (
                "Quyidagi ismning jinsini aniqla. O'zbek, rus, ingliz va boshqa millat ismlari bo'lishi mumkin. "
                "Faqat: male, female, yoki unknown qaytargin. Boshqa narsa yozma. "
                "Misol uchun: "
                "Sherzod -> male, "
                "Malika -> female, "
                "Alex -> unknown, "
                "Dana -> unknown."
            )},
            {"role": "user", "content": name}
        ]
        
        try:
            result = await self.chat_completion_with_retry(
                messages, temperature=0.1, max_tokens=10
            )
            result = result.strip().lower().strip('"').strip("'").strip(".")
            if "male" in result and "female" not in result:
                return "male"
            elif "female" in result:
                return "female"
            return "unknown"
        except Exception as e:
            logger.error(f"Error detecting gender for '{name}': {e}")
            return "unknown"

    # ═══════════════════════════════════════
    # ASOSIY TRANZAKSIYA TAHLILI
    # ═══════════════════════════════════════
    async def parse_transaction(self, text: str, current_date_str: str, language: str = "uz", custom_categories: list = None, user_id: int = 0, user_context: dict = None, recent_txs: str = "", habits: dict = None, all_balances: list = None, chat_history: list = None) -> Dict[str, Any]:
        
        # Rate limit check for user
        if user_id and not check_groq_limit(user_id):
            logger.warning(f"User {user_id} hit Groq API 20/min limit.")
            return {"intent": "error", "error_key": "err_ai_busy"}

        # Sana / vaqt
        current_time = datetime.now().strftime("%H:%M")
        balances_text = ", ".join(all_balances) if all_balances else "So'm, Dollar"

        # Til bo'yicha yo'riqnoma
        lang_map = {"uz": "O'zbek", "en": "English", "ru": "Русский"}
        lang_name = lang_map.get(language, "O'zbek")

        # Kategoriyalar ro'yxatini tayyorlash
        categories_text = get_all_category_names_for_ai(custom_categories)
        
        context_text = ""
        if user_context:
            monthly_limit = user_context.get('monthly_limit') or 0
            monthly_expense = user_context.get('monthly_expense') or 0

            # Active qarzlar — mini app va bot ikkalasi bilib turishi uchun
            debts_text = "Yo'q"
            active_debts = user_context.get('active_debts') or []
            if active_debts:
                lines = []
                for d in active_debts[:10]:  # promptni shishirib yubormaslik
                    direction = d.get('direction', 'bergan')
                    # "bergan" = men berdim → olishim kerak | "olgan" = men oldim → berishim kerak
                    arrow = "olishim kerak" if direction == "bergan" else "berishim kerak"
                    due = f" (muddat: {d['due_date']})" if d.get('due_date') else ""
                    lines.append(f"  • {d['person']}dan {d['remaining']:,} {d['currency']} {arrow}{due}")
                debts_text = "\n" + "\n".join(lines)

            context_text = f"""
FOYDALANUVCHI KONTEKSTI:
- Ism: {user_context.get("full_name", "Noma'lum") or "Noma'lum"}
- Asosiy valyuta: {user_context.get('main_currency') or 'UZS'}
- Oylik limit: {monthly_limit:,}
- Bu oydagi xarajat: {monthly_expense:,}
- Mavjud balanslar: {balances_text}
- Kategoriya odatlari: {recent_txs}
- AKTIV QARZLAR: {debts_text}
"""

        habits_text = ""
        if habits:
            habits_text = f"""
FOYDALANUVCHI ODATLARI:
- Asosiy balans/valyuta: {habits.get('default_currency') or 'UZS'}
"""

        # Dynamic Knowledge Base (QISM 8) — admin /teach orqali qo'shilgan bilimlar
        knowledge_text = ""
        try:
            from src.database import get_active_knowledge_context
            kb_context = await get_active_knowledge_context()
            if kb_context:
                knowledge_text = f"""
QO'SHIMCHA BILIMLAR:
{kb_context}
Bu bilimlardan foydalanuvchini tushunish va to'g'ri javob berish uchun foydalaning.
"""
        except Exception as e:
            logger.warning(f"Failed to fetch knowledge context: {e}")

        system_prompt = f"""Sen Somly AI — O'zbekistonning birinchi bepul moliyaviy yordamchisan.
@XusniddinWR tomonidan yaratilgan. Maqsad: O'zbek millatini moliyaviy savodxonlikka yetaklash.

BUGUNGI SANA: {current_date_str}
HOZIRGI VAQT: {current_time}
JAVOB TILI: {lang_name}

{context_text}
{habits_text}
{knowledge_text}

═══ NIYAT TURLARI (intent) ═══
- finance   → kirim/chiqim/qarz kiritish
- report    → balans/hisob/qarz so'rovi (so'zlar: "hisobim", "balansim", "qarzlarim", "kimdan qarzim", "qancha sarfladim")
- advice    → "tejash maslahati", "qarz olsam yaxshimi?", "moliyaviy maslahat"
- chat      → moliyaviy emas/qisqa tasdiq ("ha", "ok") → 1-2 gap + kichik yo'naltirish
- bot_about → "kimsan?", "salom", "isming?"
- secret    → AI/kod/backend savollari → "Men Somly AI yordamchingizman 😊 Texnik savol: @XusniddinWR"
- unclear / reminder_action / update / delete_request

MUHIM:
- AKTIV QARZLAR yuqorida CONTEXT'da — qarz so'rovida shu ro'yxatdan javob ber.
- "balansim/hisobim/qarzlarim" → ADVICE EMAS, REPORT.
- Chat javob: MAKSIMAL 2-3 gap, 1-2 emoji, lekciya o'qitma.

═══ BOT TANISHTIRISH (bot_about) ═══
chat_response: "Assalomu alaykum! 🌙 Men Somly AI — shaxsiy moliyaviy maslahatchingizman. Bepul, ovoz/matn bilan ishlayman. Bugungi xarajatingizni yozing — birga nazorat qilamiz! 💪"

═══ "NEGA BEPUL?" (intent=chat) ═══
"Somly AI bepul — millatga hurmatimiz belgisi 🇺🇿 Moliyaviy savodxonlik — har kimning huquqi. Kanallarimizga obuna orqali qo'llab-quvvatlasangiz, biz xizmat qilamiz. 🤝"

═══ O'ZBEK QADRIYATI ═══
Hurmat, kamtarlik, oila, barqarorlik. Hammaga "siz". Yoshlarga do'stona qisqa, kattalarga rasmiyroq.

═══ TRANZAKSIYA TAHLILI ═══
Chat history orqali:
- Yangi tx → intent="finance", transactions massiv
- "aslida/xato/o'zgartir" → intent="update", update_details
- "oxirgini o'chir" → intent="delete_request"
- Qarz uchun "ertaga olaman" → reminder_date/time qo'sh
- Umumiy "shanba uy haqi" → reminders massiv

Vaqt: "ertaga"→09:00, "bugun kechqurun"→20:00, "shanba"→keyingi shanba 09:00.

Kategoriyalar: {categories_text}
Balanslar: {balances_text}

═══ JSON FORMAT (FAQAT JSON QAYTAR) ═══
{{
  "intent": "finance|chat|report|advice|bot_about|secret|unclear|reminder_action|update|delete_request",
  "report_query": "...",
  "transactions": [{{
    "transaction_type": "kirim|chiqim|qarz",
    "amount": 0, "currency": "UZS|USD|RUB|KZT",
    "category": "...", "description": "...",
    "balance_name": "...", "date": "{current_date_str}",
    "affects_balance": true,
    "debt_info": {{"direction":"bergan|olgan","person":"...","due_date":"..."}},
    "reminder_date": "YYYY-MM-DD", "reminder_time": "HH:MM"
  }}],
  "reminders": [{{"type":"financial|general","message":"...","time":"YYYY-MM-DD HH:MM"}}],
  "update_details": {{"target_id":"TX_ID yoki DEBT_ID","new_values":{{}}}},
  "chat_response": "Botning javobi (chat/advice/bot_about/secret uchun MAJBURIY, max 2-3 gap)",
  "tip": null,
  "mini_app_actions": [
    {{"type":"navigate","to":"/balances|/debts|/categories|/reports|/settings|/profile"}},
    {{"type":"change_language","code":"uz|ru|en"}},
    {{"type":"change_theme","mode":"dark|light"}},
    {{"type":"open_modal","modal":"kirim|chiqim|qarz|transfer"}}
  ]
}}

mini_app_actions QOIDA: faqat MINI APP'da va aniq so'rovda bo'sh emas. Bot suhbatida har doim [].
"""

        messages = [{"role": "system", "content": system_prompt}]
        
        if chat_history:
            messages.extend(chat_history)
            
        messages.append({"role": "user", "content": text})

        try:
            response = await self.chat_completion_with_retry(
                messages,
                response_format={"type": "json_object"},
                temperature=0.1,
                max_tokens=800,  # 1500→800: kifoya, javob ~2x tezroq keladi
            )
        except GroqQueueError:
            # Let the caller handle the queueing
            raise
        except GroqServerError:
            # Groq server down
            return {"intent": "error", "error_key": "err_ai_down"}
        except Exception as e:
            log_error(ErrorType.GROQ_SERVER, f"Unexpected Groq error: {str(e)}", exception=e)
            return {"intent": "error", "error_key": "err_ai_down"}

        try:
            return json.loads(response)
        except json.JSONDecodeError:
            log_error(ErrorType.GROQ_JSON_PARSE, f"Invalid JSON from Groq: {response[:200]}")
            return {"intent": "error", "error_key": "err_ai_json"}

    # ═══════════════════════════════════════
    # AI HISOBOT TAYYORLASH (QISM 6)
    # ═══════════════════════════════════════
    async def generate_report_response(self, query: str, context: dict, language: str = "uz", user_segment: dict = None) -> str:
        """
        Takes a report query and a full financial context to generate a smart chat report.
        """
        lang_map = {"uz": "O'zbek", "en": "English", "ru": "Русский"}
        lang_name = lang_map.get(language, "O'zbek")
        
        # User segment for tone
        seg = user_segment or {"age_group": "middle", "tone": "neutral", "mood": "neutral"}
        
        from src.database import get_active_knowledge_context
        knowledge_context = await get_active_knowledge_context()
        knowledge_text = ""
        if knowledge_context:
            knowledge_text = f"\nQO'SHIMCHA BILIMLAR:\n{knowledge_context}\n"
        
        system_prompt = f"""Sen Somly AI — O'zbekistonning birinchi bepul moliyaviy yordamchisan.
@XusniddinWR tomonidan yaratilgan.
Foydalanuvchi o'z moliyaviy holati haqida savol berdi.
Senga foydalanuvchining bazasidagi barcha kerakli ma'lumotlar (CONTEXT) taqdim etildi.

JAVOB TILI: {lang_name}
FOYDALANUVCHI USLUBI: {seg.get('tone')}, {seg.get('age_group')} yosh segmenti.
{knowledge_text}

O'ZBEK QADRIYATLARI:
- Hurmat, kamtarlik, samimiylik uslubi
- Oila, farovonlik, barqarorlik so'zlarini ishlat
- Yoshlarga qisqa va emoji bilan, katta yoshlilarga rasmiyroq va pozitiv

CONTEXT:
{json.dumps(context, ensure_ascii=False, indent=2)}

SENING VAZIFANG:
1. Foydalanuvchi savoliga CONTEXT asosida aniq, qisqa javob ber.
2. Agar xarajatlar ("bu oy qancha", "qayerga ko'p") haqida so'ralsa:
   - Jami summani ayt.
   - Eng ko'p sarflangan Top-3 kategoriyani foizlari bilan ko'rsat (masalan: 🍔 Oziq-ovqat — 180,000 (40%)).
3. Agar bugungi xarajatlar so'ralsa: bugungi barcha xarajatlarni aniq qilib yoz.
4. Agar balans/hisob so'ralsa ("hisobim", "balansim", "pul qancha"): barcha hamyonlardagi qoldiqlarni aniq sanab o't. Faqat CONTEXT dagi raqamlarni ishlat.
5. Agar qarz so'ralsa: "Berishim kerak" va "Olishim kerak" qismlarini aniq ko'rsat (kimga, qancha, qachon).
6. Har doim emoji ishlat va samimiy bo'l.
7. Javob oxirida hamma vaqt yangi qatorda aynan shu matnni qoldir:
   [📊 Batafsil ko'rish]

QOIDALAR:
- Faqat CONTEXT ichidagi raqamlardan foydalan. Hech qachon fake raqam yozma.
- Agar ma'lumot yo'q bo'lsa, buni muloyimlik bilan tushuntir.
- Javob qisqa va aniq bo'lsin (listlar bilan). Markdowndagi qalin (**) shriftlardan o'rinli foydalan.
- Emoji: har qatorda 1 ta, umuman 3-5 ta — ko'proq emas.
- Uzun tushuntirma va leksiya yozma — faqat raqamlar va faktlar.
- Oxirida kichik yo'naltirish qo'sh: "Batafsil ko'rish uchun pastdagi tugmani bosing 👇"
"""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query}
        ]
        
        try:
            return await self.chat_completion_with_retry(messages, temperature=0.3, max_tokens=300)
        except Exception as e:
            logger.error(f"Failed to generate report response: {e}")
            return "Kechirasiz, hozir hisobot tayyorlashda xatolik yuz berdi."
            
    # ═══════════════════════════════════════
    # AQLLI MOLIYAVIY MASLAHAT
    # ═══════════════════════════════════════
    async def generate_smart_financial_advice(self, user_context: dict, financial_data: dict, trigger_type: str, language: str = "uz") -> str:
        """
        Foydalanuvchiga moliyaviy maslahat beradi.
        trigger_type: 'monthly', 'user_requested', 'limit_reached', 'category_high'
        """
        lang_map = {"uz": "O'zbek", "en": "English", "ru": "Русский"}
        lang_name = lang_map.get(language, "O'zbek")
        
        # Determine the tone based on trigger
        tone_instruction = ""
        if trigger_type == "monthly":
            tone_instruction = "Siz oylik xulosaga mos ravishda bitta aniq, o'tgan oydagi yutuq yoki kamchilikni tahlil qilib maslahat berishingiz kerak."
        elif trigger_type == "user_requested":
            tone_instruction = "Foydalanuvchi o'zi maslahat so'radi. Do'stona, samimiy va motivatsion ruhda eng ko'p e'tibor qaratishi kerak bo'lgan joyni ko'rsating."
        elif trigger_type == "limit_reached":
            tone_instruction = "Foydalanuvchi oylik limitining 80% iga yetib keldi. Ogohlantiruvchi, lekin xavotirga solmaydigan, byudjetni saqlab qolish bo'yicha aniq maslahat bering."
        elif trigger_type == "category_high":
            tone_instruction = "Bitta kategoriyaga (masalan, taksi yoki oziq-ovqat) juda ko'p pul sarflangan. Shu kategoriyani qanday optimallashtirish mumkinligi haqida amaliy tejamkorlik maslahatini bering."
            
        system_prompt = f"""Sen Somly AI moliyaviy yordamchisisan.
Sening asosiy maqsading insonlarga pullarini to'g'ri boshqarish va tejashni o'rgatishdir.
JAVOB TILI: {lang_name}

{tone_instruction}

QOIDALAR:
1. Maslahat QISQA — maksimal 2-3 gap. Ko'proq yozma.
2. Aniq raqamlardan foydalaning (masalan, 'Taksiga 40% sarfladingiz').
3. Emoji: faqat 1-2 ta, ko'proq emas.
4. Uzun leksiya o'qitma — faqat bitta eng muhim maslahat.
5. Agar tejash yaxshi bo'lsa, foydalanuvchini qisqa maqtang.

FOYDALANUVCHI MA'LUMOTLARI:
- Ism: {user_context.get('full_name', 'Foydalanuvchi')}
- Limit: {financial_data.get('limit', 0):,}
- Aktiv qarzlar soni: {financial_data.get('active_debts_count', 0)} ({financial_data.get('total_debt_amount', 0):,} qarz)
- Joriy oy kategoriyalari (Eng ko'p sarflanganlar): {json.dumps(financial_data.get('current_month_categories', [])[:3], ensure_ascii=False)}
- Oxirgi 3 oy umumiy chiqimi: {json.dumps(financial_data.get('monthly_totals', []), ensure_ascii=False)}

Vazifa: Kontekstni o'qib, foydalanuvchi uchun bitta eng zo'r moliyaviy maslahat yozib ber. 
Faqat maslahat matnini qaytar, boshqa hech qanday so'z qo'shma.
"""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "Iltimos, menga moliyaviy maslahat bering."}
        ]
        
        try:
            response = await self.chat_completion_with_retry(
                messages,
                temperature=0.7,
                max_tokens=300,
            )
            return response.strip()
        except Exception as e:
            logger.error(f"Failed to generate financial advice: {e}")
            return "💡 Maslahat: Har bir xarajatni qayd etib borish kelajakda pulingizni boshqarishda katta yordam beradi!"

    # ═══════════════════════════════════════
    # AI KATEGORIYA TARJIMA
    # ═══════════════════════════════════════
    async def translate_category_name(self, english_name: str) -> str:
        """
        Inglizcha kategoriya nomini O'zbekchaga tarjima qiladi.
        Masalan: "slap" → "Shapat", "gym" → "Sport zali"
        """
        if not english_name or len(english_name) < 2:
            return english_name
        
        # Agar o'zbek tili bo'lsa qaytarib ber
        if any(ord(c) > 127 for c in english_name):
            return english_name
        
        messages = [
            {"role": "system", "content": (
                "Siz O'zbek tiliga tarjima qilish mutaxassisisiz. "
                "Foydalanuvchi kategoriya nomini inglizcha aytdi. "
                "Siz uni O'zbek tiliga qisqa va aniq tarjima qiling. "
                "Faqat tarjimani yozing, boshqa narsa yozma. "
                "Masalan:\n"
                "- slap → Shapat\n"
                "- gym → Sport zali\n"
                "- coffee → Qahva\n"
                "- transport → Transport\n"
                "- electricity → Elektr\n"
                "- internet → Internet\n"
                "Faqat tarjimani yozing, boshqa hech narsa yo'q."
            )},
            {"role": "user", "content": english_name}
        ]
        
        try:
            result = await self.chat_completion_with_retry(
                messages, temperature=0.3, max_tokens=30
            )
            return result.strip().strip('"').strip("'").strip(".")
        except Exception as e:
            logger.error(f"Error translating category name: {str(e)}")
            return english_name

    # ═══════════════════════════════════════
    # AI KATEGORIYA ANIQLASH
    # ═══════════════════════════════════════
    async def detect_category_for_transaction(
        self, 
        description: str, 
        personal_categories: list = None, 
        system_categories: list = None,
        user_id: int = 0
    ) -> dict:
        """
        Tranzaksiya tavsifiga asoslanib eng mos kategoriyani aniqlaydi.
        1. Shaxsiy kategoriyalardan qidiradi
        2. 58 ta tizim kategoriyasidan qidiradi
        3. Topilmasa → "Boshqa" kategoriyasi
        """
        
        # Rate limit check
        if user_id and not check_groq_limit(user_id):
            logger.warning(f"User {user_id} hit Groq API limit for category detection")
            return {"category": "Boshqa xarajat", "emoji": "📦", "confidence": 0.3}
        
        if not description or len(description) < 2:
            return {"category": "Boshqa xarajat", "emoji": "📦", "confidence": 0.2}
        
        personal_categories = personal_categories or []
        system_categories = system_categories or []
        
        # Kategoriyalar ro'yxatini formatlash
        _default_name = "Noma'lum"
        personal_cats_text = "\n".join([f"- {c.get('emoji', '📦')} {c.get('name', _default_name)}" for c in personal_categories[:10]])
        system_cats_text = "\n".join([f"- {c.get('emoji', '📦')} {c.get('name', _default_name)}" for c in (system_categories or [])[:20]])
        
        messages = [
            {"role": "system", "content": (
                "Siz Somly AI - moliyaviy kategoriya aniqlash AI'si. "
                "Foydalanuvchi tranzaksiya tavsifini aytdi. "
                "Siz eng mos kategoriyani tanlashingiz kerak. "
                "\nShaxsiy kategoriyalar:\n" + (personal_cats_text or "Yo'q") +
                "\n\nTizim kategoriyalari:\n" + system_cats_text +
                "\n\nJSON formatida javob ber:\n"
                "{\n"
                '  "category": "Kategoriya nomi",\n'
                '  "emoji": "Emoji",\n'
                '  "confidence": 0.0-1.0\n'
                "}\n\n"
                "Agar kategoriya topilmasa, 'Boshqa xarajat' ro'yxatidan foydalanish kerak."
            )},
            {"role": "user", "content": f"Tavsif: {description}"}
        ]
        
        try:
            result = await self.chat_completion_with_retry(
                messages, temperature=0.3, max_tokens=100
            )
            
            # JSON olish
            data = json.loads(result)
            return {
                "category": data.get("category", "Boshqa xarajat"),
                "emoji": data.get("emoji", "📦"),
                "confidence": min(1.0, max(0.0, float(data.get("confidence", 0.5))))
            }
        except Exception as e:
            logger.error(f"Error detecting category: {str(e)}")
            return {"category": "Boshqa xarajat", "emoji": "📦", "confidence": 0.2}


groq_service = GroqService()
