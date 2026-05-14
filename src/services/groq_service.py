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
from datetime import datetime, timedelta
from typing import List, Dict, Any
from dataclasses import dataclass
from groq import AsyncGroq, APIStatusError, APITimeoutError, APIConnectionError
from src.config import GROQ_API_KEYS, GROQ_MODEL, ADMIN_ID, BOT_TOKEN
from src.categories import get_all_category_names_for_ai
from src.services.i18n import t
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


@dataclass
class KeyStats:
    key: str
    index: int
    client: AsyncGroq
    status: str = "active" # "active", "cooling", "exhausted"
    requests_count: int = 0
    last_error_time: float = 0.0
    connection_errors: int = 0


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

    async def validate_keys_on_startup(self):
        """Test each key with a minimal API call at startup. Mark invalid ones immediately."""
        for ks in self.keys_stats:
            try:
                response = await ks.client.chat.completions.create(
                    messages=[{"role": "user", "content": "hi"}],
                    model=GROQ_MODEL,
                    max_tokens=5,
                )
                logger.info(f"Key {ks.index+1}: VALID")
            except APIStatusError as e:
                status_code = getattr(e, 'status_code', 0)
                if status_code == 401:
                    ks.status = "exhausted"
                    ks.last_error_time = time.time()
                    logger.warning(f"Key {ks.index+1}: INVALID (401) — disabled permanently")
                elif status_code == 429:
                    # Rate limited but key is valid
                    logger.info(f"Key {ks.index+1}: VALID (rate limited, will cool down)")
                else:
                    logger.warning(f"Key {ks.index+1}: Error {status_code} during validation")
            except Exception as e:
                logger.warning(f"Key {ks.index+1}: Validation error — {str(e)[:100]}")
        
        active = sum(1 for ks in self.keys_stats if ks.status == "active")
        logger.info(f"Key validation complete: {active}/{len(self.keys_stats)} active")
        if active == 0:
            logger.error("WARNING: No valid API keys! All requests will fail.")
            await self.alert_admin("🚨 BARCHA Groq API kalitlari yaroqsiz! Botga yangi kalitlar kerak.")

    async def alert_admin(self, message: str):
        try:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
            async with aiohttp.ClientSession() as session:
                await session.post(url, json={"chat_id": ADMIN_ID, "text": message})
        except Exception as e:
            logger.error(f"Failed to send admin alert: {e}")

    def get_best_key(self) -> KeyStats:
        now = time.time()
        # 1. Check if any cooling key can be reactivated (NOT exhausted/401 keys)
        for ks in self.keys_stats:
            if ks.status == "cooling":
                if now - ks.last_error_time > 60:
                    ks.status = "active"
                    ks.connection_errors = 0
                    logger.info(f"Groq API Key {ks.index+1} reactivated after cooling.")

        # 2. Find the active key with the minimum requests
        active_keys = [ks for ks in self.keys_stats if ks.status == "active"]
        if active_keys:
            best_key = min(active_keys, key=lambda x: x.requests_count)
            return best_key
        
        # 3. All keys are either cooling or exhausted
        exhausted_keys = [ks for ks in self.keys_stats if ks.status == "exhausted"]
        if len(exhausted_keys) == len(self.keys_stats):
            raise GroqServerError("All API keys are permanently exhausted (401/Quota).")
        
        raise GroqQueueError("All keys are exhausted or cooling. Queueing required.")

    async def chat_completion_with_retry(self, messages: List[Dict], **kwargs) -> str:
        attempts = 0
        max_retries = len(self.keys_stats) * 2

        while attempts < max_retries:
            try:
                ks = self.get_best_key()
            except GroqQueueError:
                raise # immediately propagate so handler can queue

            try:
                response = await ks.client.chat.completions.create(
                    messages=messages,
                    model=GROQ_MODEL,
                    **kwargs
                )
                ks.requests_count += 1
                ks.connection_errors = 0
                return response.choices[0].message.content
            except APIStatusError as e:
                status_code = getattr(e, 'status_code', 0)
                error_str = str(e)
                logger.error(f"Groq API Error (key {ks.index+1}): {error_str}")

                if status_code == 429 or "rate" in error_str.lower() or status_code == 403:
                    ks.status = "cooling"
                    ks.last_error_time = time.time()
                    log_error(ErrorType.GROQ_RATE_LIMIT, f"Key {ks.index+1} rate limited (cooling)", exception=e)
                elif status_code == 401 or "invalid_api_key" in error_str.lower():
                    ks.status = "exhausted"
                    ks.last_error_time = time.time()
                    log_error(ErrorType.GROQ_RATE_LIMIT, f"Key {ks.index+1} invalid (401)", exception=e)
                    asyncio.create_task(self.alert_admin(f"🚨 Groq API Key {ks.index+1} is INVALID (401 Unauthorized). It has been disabled."))
                elif "quota" in error_str.lower():
                    ks.status = "exhausted"
                    ks.last_error_time = time.time()
                    log_error(ErrorType.GROQ_RATE_LIMIT, f"Key {ks.index+1} quota exceeded", exception=e)
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
                    model=GROQ_MODEL,
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
        attempts = 0
        max_retries = len(self.keys_stats) * 2
        models_to_try = ["whisper-large-v3-turbo", "whisper-large-v3"]

        while attempts < max_retries:
            try:
                ks = self.get_best_key()
            except GroqQueueError:
                raise

            model = models_to_try[0] if attempts < max_retries // 2 else models_to_try[-1]

            try:
                with open(file_path, "rb") as file:
                    file_data = file.read()
                
                # Use filename with proper extension for Groq
                fname = os.path.basename(file_path)
                transcription = await ks.client.audio.transcriptions.create(
                    file=(fname, file_data),
                    model=model,
                    response_format="json",
                )
                ks.requests_count += 1
                ks.connection_errors = 0
                logger.info(f"Transcription success (model={model}, key={ks.index+1}): {transcription.text[:80]}...")
                return transcription.text
            except APIStatusError as e:
                status_code = getattr(e, 'status_code', 0)
                error_str = str(e)
                logger.error(f"Groq Audio Error (key {ks.index+1}, model={model}): {error_str}")

                if status_code == 429 or "rate" in error_str.lower() or status_code == 403:
                    ks.status = "cooling"
                    ks.last_error_time = time.time()
                elif status_code == 401 or "invalid_api_key" in error_str.lower():
                    ks.status = "exhausted"
                    ks.last_error_time = time.time()
                    asyncio.create_task(self.alert_admin(f"🚨 Groq API Key {ks.index+1} is INVALID (401 Unauthorized) for Audio. It has been disabled."))
                elif "quota" in error_str.lower():
                    ks.status = "exhausted"
                    ks.last_error_time = time.time()
                    asyncio.create_task(self.alert_admin(f"🚨 Groq API Key {ks.index+1} EXHAUSTED (Audio Quota)."))
                elif status_code >= 500:
                    raise GroqServerError(f"Groq server error: {status_code}")
                else:
                    raise e
            except (APITimeoutError, APIConnectionError) as e:
                logger.error(f"Groq Audio connection error (key {ks.index+1}): {str(e)}")
                ks.connection_errors += 1
                if ks.connection_errors >= 3:
                    ks.status = "cooling"
                    ks.last_error_time = time.time()
                
            attempts += 1

        raise GroqQueueError("All API keys exhausted for audio")

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

        # ... (date calculations)
        today = datetime.strptime(current_date_str, "%Y-%m-%d")
        yesterday = (today - timedelta(days=1)).strftime("%Y-%m-%d")
        tomorrow = (today + timedelta(days=1)).strftime("%Y-%m-%d")
        current_time = datetime.now().strftime("%H:%M")

        balances_text = ", ".join(all_balances) if all_balances else "So'm, Dollar"

        # Kechagi va ertangi sanani hisoblash
        today = datetime.strptime(current_date_str, "%Y-%m-%d")
        yesterday = (today - timedelta(days=1)).strftime("%Y-%m-%d")
        tomorrow = (today + timedelta(days=1)).strftime("%Y-%m-%d")
        current_time = datetime.now().strftime("%H:%M")

        # Til bo'yicha yo'riqnoma
        lang_map = {"uz": "O'zbek", "en": "English", "ru": "Русский"}
        lang_name = lang_map.get(language, "O'zbek")

        # Kategoriyalar ro'yxatini tayyorlash
        categories_text = get_all_category_names_for_ai(custom_categories)
        
        context_text = ""
        if user_context:
            monthly_limit = user_context.get('monthly_limit') or 0
            monthly_expense = user_context.get('monthly_expense') or 0
            context_text = f"""
FOYDALANUVCHI KONTEKSTI:
- Ism: {user_context.get("full_name", "Noma'lum") or "Noma'lum"}
- Asosiy valyuta: {user_context.get('main_currency') or 'UZS'}
- Oylik limit: {monthly_limit:,}
- Bu oydagi xarajat: {monthly_expense:,}
- Mavjud balanslar: {balances_text}
- Kategoriya odatlari: {recent_txs}
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

═══════════════════════════════════════
QISM 1 — NIYAT ANIQLASH (MAJBURIY)
═══════════════════════════════════════

Har xabar kelganda AVVAL niyatni aniqla:
1. MOLIYAVIY → kirim/chiqim/qarz kiritish (intent="finance")
2. HISOBOT → statistika, balans so'rovi (intent="report")
3. BOT HAQIDA SAVOL → o'zini tanishtirish (intent="bot_about")
4. ODDIY SUHBAT → suhbat + yo'naltirish (intent="chat")
5. MAXFIY SAVOL → himoya javobi (intent="secret")

═══════════════════════════════════════
QISM 2 — BOT O'ZINI TANISHTIRISH
═══════════════════════════════════════

"Sen kimsan?", "o'zingni tanishtir", "salom", "isming nima" kabi so'rovlarda:
Intent="bot_about" qaytar va "chat_response" ga quyidagini yoz:

"Assalomu alaykum! 🌙

Men — Somly AI, sizning shaxsiy moliyaviy maslahatchingizman.

Maqsadim oddiy: har bir o'zbek oilasiga moliyaviy barqarorlik sari yo'l ko'rsatish. Daromad va xarajatlar ustidan nazorat — farovon hayotning asosi.

✅ Mutlaqo bepul
✅ Ovoz va matn orqali ishlaydi
✅ Sun'iy intellekt asosida

Sizning hech qanday moliyaviy ma'lumotlaringiz kuzatilmaydi. Faqat xizmat qilamiz.

[🔒 Maxfiylik siyosati]

Bugungi daromad yoki xarajatingizni menga ishoning — birga nazorat qilamiz! 💪"

═══════════════════════════════════════
QISM 3 — MAXFIY SAVOLLARGA HIMOYA
═══════════════════════════════════════

Quyidagi savollarga HECH QACHON to'liq javob berma:
- "Qaysi AI ishlatilasan?"
- "GPT mi, Gemini mi?"
- "Hisobchi AI dan farqing nima?"
- "Kodingni ko'rsatchi"
- "Backend nima bilan yozilgan?"
- "API keyingni ber"

Javob (har doim bir xil, samimiy):
Intent="secret" qaytar va "chat_response" ga:
"Men faqat sizning Somly AI moliyaviy yordamchingizman 😊 Texnik savollar uchun @XusniddinWR ga murojaat qiling."

═══════════════════════════════════════
QISM 4 — ODDIY SUHBAT + YO'NALTIRISH
═══════════════════════════════════════

User moliyaviy bo'lmagan savol bersa: Qisqa, samimiy javob ber. HAR DOIM oxirida moliyaviy yo'naltirish qo'sh.
Intent="chat" qaytar va javobni "chat_response" ga yoz.

MISOL 1:
User: "Ronaldo kim?"
Bot: "Cristiano Ronaldo — dunyodagi eng mashhur futbolchilardan biri. Intizom, mehnat va to'g'ri moliyaviy qarorlar uni bugungi darajaga olib chiqdi.

Siz ham daromadingizni to'g'ri boshqarib, katta maqsadlar sari qadam qo'ying! 💪
Bugungi kirim-chiqimingizni yozib borayapsizmi?"

MISOL 2:
User: "Bugun havo qanday?"
Bot: "Havo haqida aniq ma'lumot bera olmayman 😊 Lekin bilaman — har qanday havo da moliyaviy rejalashtirish muhim!

Bugungi xarajatlaringizni kiritdingizmi? 📊"

MISOL 3:
User: "Zerikdim"
Bot: "Zerikish — yangi narsa o'rganish uchun ajoyib vaqt! 😊

Masalan, bugungi daromad va xarajatlaringizni tahlil qiling — bu 2 daqiqa vaqt oladi va moliyaviy rasmingizni ko'rsatadi.

Boshlaylikmi? 💰"

YO'NALTIRISH IBORALARI (har doim birini qo'sh):
- "Bugungi xarajatlaringizni kiritdingizmi?"
- "Moliyaviy maqsadingiz bormi?"
- "Daromadingizni kuzatyapsizmi?"
- "Boshlaylikmi? 💰"
- "Bugungi kirim-chiqimingizni yozib borayapsizmi?"

═══════════════════════════════════════
QISM 5 — O'ZBEK QADRIYATLARI
═══════════════════════════════════════

Bot doim O'zbek milliy qadriyatlariga mos gapiradi:
- "Assalomu alaykum" bilan boshlash (birinchi suhbatlarda)
- Hurmat, kamtarlik uslubi
- Oila, farovonlik, kelajak so'zlarini ishlatish
- "Millat", "yurt", "barqarorlik" tushunchalariga murojaat
- Yosh user (18-24): "siz", lekin qisqa va do'stona
- Katta yoshli: "siz", rasmiy va hurmatli

═══════════════════════════════════════
QISM 6 — MAXFIYLIK SIYOSATI
═══════════════════════════════════════

Bot o'zini tanitganda yoki maxfiylik haqida savol bo'lganda inline button beriladi:
[🔒 Maxfiylik siyosati]
Bosilganda Mini App ochiladi va Maxfiylik siyosati bo'limiga o'tadi.

Maxfiylik siyosati matni:

"Somly AI Maxfiylik Siyosati

Somly AI siz ishonib topshirgan moliyaviy ma'lumotlaringizni — kirim, chiqim va qarz ma'lumotlarini — hech qachon kuzatmaydi, tahlil qilmaydi yoki uchinchi shaxslarga taqdim etmaydi.

Biz faqatgina quyidagi umumiy ma'lumotlarni saqlaymiz:
- Yoshingiz
- Joylashuvingiz (viloyat/davlat)
- Telegram ism va raqamingiz

Ushbu ma'lumotlar faqatgina sizga samarali va maqsadli reklama ko'rsatish maqsadida ishlatiladi.

Ma'lumotlaringiz hech qachon, hech qayerga sotilmaydi.
Barcha ma'lumotlar xavfsiz serverlarimizda muhofaza ostida.

Shikoyat va takliflar uchun: @XusniddinWR"

═══════════════════════════════════════
QISM 7 — "NEGA BEPUL?" SAVOLIGA JAVOB
═══════════════════════════════════════

"Nega bepul?", "nima uchun tekin?" so'rovlarida:
Intent="chat" qaytar va "chat_response" ga:

"Somly AI ning bepulligi — bu bizning millatga bo'lgan hurmatimiz belgisi. 🇺🇿

Moliyaviy savodxonlik — har bir insonning huquqi, imtiyoz emas.

Biz kanallarimizga obuna bo'lgan foydalanuvchilar orqali rivojlanamiz.
Siz obuna bo'lish orqali bizni qo'llab-quvvatlaysiz — biz esa sizga bepul xizmat ko'rsatamiz.

Bu — o'zaro hurmat asosidagi hamkorlik. 🤝"

═══════════════════════════════════════
QISM 8 — MOLIYAVIY MASLAHAT (ADVICE)
═══════════════════════════════════════

"Qanday tejasam bo'ladi?", "Qarz olsam yaxshimi?", "Mening moliyaviy holatim qanday?" kabi savollarga:
Foydalanuvchining CONTEXT ma'lumotlariga qarab maslahat bering. Masalan: xarajati ko'p bo'lsa tejamkorlik, qarz haqida ijobiy/salbiy tahlil.
CHEGARA: Tibbiyot, huquq, siyosat → "Bu savol mening doiramdan tashqarida. Moliyaviy savollar uchun bu yerdaman! 😊"
Intent="advice" qaytar va javobni "chat_response" ga yoz.

═══════════════════════════════════════
QISM 7 — TRANZAKSIYA TAHLILI
═══════════════════════════════════════

Senga CHAT HISTORY (oldin yozishilgan xabarlar) yuboriladi. Ular orqali:

1. YANGI TRANZAKSIYA: Moliyaviy xarajat/kirim/qarz → intent="finance" va transactions massiviga yoz.
2. TARIXGA BOG'LIQ TUZATISH: "aslida", "yo'q", "xato", "o'zgartir" → intent="update", update_details ga yoz.
3. O'CHIRISH: "Oxirgini o'chir" → intent="delete_request".
4. ESLATMA / VAQT KONTEKSTI:
   A) QARZ UCHUN: "Sardorga 10k berdim, ertaga olaman" → transactions ichidagi qarzga "reminder_date" va "reminder_time" qo'sh.
   B) UMUMIY ESLATMA: "Shanba kuni uy haqi to'lash" → "reminders" massiviga qo'sh.
   
   VAQT HISOB-KITOBI:
   - "hozir" → hozirgi vaqt
   - "N daqiqadan/soatdan keyin" → hisoblab yoz
   - "bugun kechqurun" → bugun 20:00
   - "ertaga" → ertaga 09:00
   - "shanba" → keyingi shanba 09:00
   - "10-may" → 10 May 09:00

QOLGAN QOIDALAR:
- intent turlari: finance | chat | report | advice | bot_about | secret | unclear | reminder_action | update | delete_request
- reminder_action: FAKATGINA foydalanuvchi kelgan eslatmaga javob bersa.
- report_query: agar intent="report" bo'lsa, hisobot so'rovi yoziladi.
- transactions massivida BARCHA amallar bo'lishi SHART.
- MAVJUD KATEGORIYALAR: {categories_text}
- KATEGORIYA YARATISH: Agar xarajat/kirim mavjud kategoriyalarning BIRTASIGA HAM mantiqan mos kelmasa, MAVJUD KATEGORIYAGA TIQISHTIRMA! Uning o'rniga o'zing eng mos va qisqa YANGI KATEGORIYA nomini yarat (masalan: 'Gullar', 'Sovg'alar', 'Kiyim-kechak').
- MAVJUD BALANSLAR: {balances_text}

JSON FORMATI:
{{
  "intent": "finance|chat|report|advice|bot_about|secret|unclear|reminder_action|update|delete_request",
  "report_query": "Foydalanuvchi so'rovi",
  "transactions": [
    {{
      "transaction_type": "kirim|chiqim|qarz",
      "amount": 15000,
      "currency": "UZS|USD|RUB|KZT",
      "category": "kategoriya nomi",
      "description": "izoh",
      "balance_name": "Balans nomi",
      "date": "{current_date_str}",
      "affects_balance": true,
      "debt_info": {{"direction": "bergan|olgan", "person": "...", "due_date": "..."}},
      "reminder_date": "YYYY-MM-DD",
      "reminder_time": "HH:MM"
    }}
  ],
  "reminders": [{{ "type": "financial|general", "message": "...", "time": "YYYY-MM-DD HH:MM" }}],
  "update_details": {{
     "target_id": "TX_ID yoki DEBT_ID",
     "new_values": {{"amount": 150000, "description": "yangi izoh..."}}
  }},
  "chat_response": "Botning javobi (chat, advice, bot_about, secret intent uchun MAJBURIY)",
  "tip": "Maslahat yoki null"
}}

FAQAT JSON QAYTAR.
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
                max_tokens=1500,
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
1. Foydalanuvchi savoliga CONTEXT asosida aniq javob ber.
2. Agar xarajatlar ("bu oy qancha", "qayerga ko'p") haqida so'ralsa:
   - Jami summani ayt.
   - Eng ko'p sarflangan Top-3 kategoriyani foizlari bilan ko'rsat (masalan: 🍔 Oziq-ovqat — 180,000 (40%)).
3. Agar bugungi xarajatlar so'ralsa: bugungi barcha xarajatlarni aniq qilib yoz.
4. Agar balans so'ralsa: barcha hamyonlardagi qoldiqlarni sanab o't.
5. Agar qarz so'ralsa: "Berishim kerak" va "Olishim kerak" qismlarini aniq ko'rsat (kimga, qancha, qachon).
6. Har doim emoji ishlat va samimiy bo'l.
7. Javob oxirida hamma vaqt yangi qatorda aynan shu matnni qoldir:
   [📊 Batafsil ko'rish]

QOIDALAR:
- Faqat CONTEXT ichidagi raqamlardan foydalan.
- Agar ma'lumot yo'q bo'lsa, buni muloyimlik bilan tushuntir.
- Javob qisqa, tushunarli va o'qishga qulay (listlar bilan) bo'lsin. Markdowndagi qalin (**) shriftlardan o'rinli foydalan.
- HAR DOIM oxirida moliyaviy yo'naltirish qo'sh: "Moliyaviy maqsadingiz bormi?" yoki "Boshlaylikmi? 💰"
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
1. Maslahat qisqa (max 3-4 gap), tushunarli va amaliy bo'lishi kerak.
2. Aniq raqamlardan (agar mavjud bo'lsa) foydalaning (masalan, 'Siz taksiga 40% sarfladingiz').
3. O'zbekona lutf va emojilardan me'yorida foydalaning.
4. "Qarz ko'p bo'lsa", qachon qaytarish kerakligi haqida iliq eslatma qiling.
5. Agar tejash yaxshi bo'lsa, foydalanuvchini maqtab qo'ying.

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
