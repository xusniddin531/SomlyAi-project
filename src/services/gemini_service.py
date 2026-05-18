"""
Gemini AI Service.

Features:
- Gemini API integration
- Transaction parsing with enhanced 7-step analysis
- Audio transcription via File API
- Name extraction from voice
- Comprehensive error classification
"""

import json
import os
import logging
import asyncio
import time
from datetime import datetime
from typing import List, Dict, Any
from dataclasses import dataclass
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
from src.config import GEMINI_API_KEY, GEMINI_MODEL, ADMIN_ID, BOT_TOKEN
from src.categories import get_all_category_names_for_ai
from src.services.error_handler import log_error, ErrorType
import aiohttp

logger = logging.getLogger(__name__)

# User request limit
gemini_user_requests = {}
GEMINI_USER_LIMIT_1M = 20

def check_gemini_limit(user_id: int) -> bool:
    """Returns True if allowed, False if exceeded limit."""
    if not user_id:
        return True
    now = time.time()
    if user_id not in gemini_user_requests:
        gemini_user_requests[user_id] = []
    
    # Clean old requests (> 60s)
    gemini_user_requests[user_id] = [ts for ts in gemini_user_requests[user_id] if now - ts <= 60]
    
    if len(gemini_user_requests[user_id]) >= GEMINI_USER_LIMIT_1M:
        return False
        
    gemini_user_requests[user_id].append(now)
    return True


class GeminiServerError(Exception):
    """Gemini returned 500+ server error."""
    pass

class GeminiInvalidAudioError(Exception):
    """Audio file rejected."""
    pass

class GeminiService:
    def __init__(self):
        if not GEMINI_API_KEY:
            logger.error("GEMINI_API_KEY is missing!")
        else:
            genai.configure(api_key=GEMINI_API_KEY)
            logger.info("GeminiService initialized")
            
        self.active_model = GEMINI_MODEL

    async def validate_keys_on_startup(self):
        """Test API key at startup."""
        if not GEMINI_API_KEY:
            logger.error("WARNING: No valid API keys! All requests will fail.")
            await self.alert_admin("🚨 GEMINI_API_KEY .env faylida topilmadi!")
            return

        try:
            model = genai.GenerativeModel(self.active_model)
            response = await asyncio.to_thread(
                model.generate_content,
                "hi",
            )
            logger.info("Gemini API Key: VALID")
        except Exception as e:
            logger.warning(f"Validation error: {e}")
            await self.alert_admin(f"🚨 Gemini API ishlamayapti: {str(e)[:200]}")

    async def alert_admin(self, message: str):
        try:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
            async with aiohttp.ClientSession() as session:
                await session.post(url, json={"chat_id": ADMIN_ID, "text": message})
        except Exception as e:
            logger.error(f"Failed to send admin alert: {e}")

    def _convert_messages_to_gemini(self, messages: List[Dict]) -> tuple:
        """Convert OpenAI style messages to Gemini (system_instruction + history)."""
        system_instruction = None
        history = []
        for msg in messages:
            role = msg.get("role")
            content = msg.get("content", "")
            if role == "system":
                system_instruction = content
            elif role == "user":
                history.append({"role": "user", "parts": [content]})
            elif role == "assistant":
                history.append({"role": "model", "parts": [content]})
        return system_instruction, history

    async def chat_completion_with_retry(self, messages: List[Dict], **kwargs) -> str:
        """Wrapper for generate_content to simulate the previous chat_completion_with_retry."""
        system_instruction, history = self._convert_messages_to_gemini(messages)
        
        # Determine format if json is requested
        generation_config = genai.types.GenerationConfig()
        
        if kwargs.get("temperature") is not None:
            generation_config.temperature = kwargs["temperature"]
        if kwargs.get("max_tokens") is not None:
            generation_config.max_output_tokens = kwargs["max_tokens"]
        
        response_format = kwargs.get("response_format")
        if response_format and response_format.get("type") == "json_object":
            generation_config.response_mime_type = "application/json"
            
        model = genai.GenerativeModel(
            model_name=self.active_model,
            system_instruction=system_instruction,
            generation_config=generation_config,
            safety_settings={
                HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
            }
        )
        
        # The prompt is the last user message, the rest is history
        if not history:
            prompt = ""
        else:
            prompt = history[-1]["parts"][0]
            history = history[:-1] # Remove the last message from history as it's the current prompt

        try:
            if history:
                chat = model.start_chat(history=history)
                response = await asyncio.to_thread(chat.send_message, prompt)
            else:
                response = await asyncio.to_thread(model.generate_content, prompt)
                
            return response.text
        except Exception as e:
            logger.error(f"Gemini API Error: {str(e)}")
            raise GeminiServerError(f"Gemini Error: {e}")

    async def stream_chat_completion_with_retry(self, messages: List[Dict], **kwargs):
        """Stream response."""
        system_instruction, history = self._convert_messages_to_gemini(messages)
        
        model = genai.GenerativeModel(
            model_name=self.active_model,
            system_instruction=system_instruction,
            safety_settings={
                HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
            }
        )
        
        if not history:
            yield "Xatolik: Matn kiritilmadi."
            return
            
        prompt = history[-1]["parts"][0]
        history = history[:-1]

        try:
            if history:
                chat = model.start_chat(history=history)
                # To make it async generator compatible
                response = await asyncio.to_thread(chat.send_message, prompt, stream=True)
            else:
                response = await asyncio.to_thread(model.generate_content, prompt, stream=True)
                
            for chunk in response:
                if chunk.text:
                    yield chunk.text
        except Exception as e:
            logger.error(f"Gemini Stream Error: {e}")
            yield "Xatolik: Tizim hozircha javob bera olmaydi."

    async def transcribe_audio_with_retry(self, file_path: str) -> str:
        """Transcribe audio using Gemini."""
        file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0
        fname = os.path.basename(file_path)
        logger.info(f"Gemini Audio start: file={fname}, size={file_size} bytes")

        try:
            # Upload file to Gemini
            myfile = await asyncio.to_thread(genai.upload_file, file_path)
            
            model = genai.GenerativeModel(self.active_model)
            prompt = "Iltimos, ushbu audioni diqqat bilan eshitib, so'zma-so'z matnga o'giring. Faqat eshitilgan matnni yozing, izoh yoki boshqa narsa qo'shmang."
            
            response = await asyncio.to_thread(model.generate_content, [myfile, prompt])
            
            # Clean up the file from Gemini servers
            await asyncio.to_thread(myfile.delete)
            
            text = response.text.strip()
            logger.info(f"Gemini Audio success: {text[:80]}...")
            return text
        except FileNotFoundError:
            logger.error(f"Gemini Audio: file not found: {file_path}")
            raise GeminiInvalidAudioError(f"Audio file missing: {file_path}")
        except Exception as e:
            logger.error(f"Gemini Audio error: {e}")
            raise GeminiServerError(f"Audio processing error: {e}")

    # ═══════════════════════════════════════
    # ISMNI AJRATIB OLISH (ovozdan)
    # ═══════════════════════════════════════
    async def extract_name(self, transcribed_text: str) -> str:
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
            return result.strip().strip('"').strip("'").strip(".")
        except Exception:
            return transcribed_text.strip()

    # ═══════════════════════════════════════
    # JINSNI ANIQLASH (AI orqali)
    # ═══════════════════════════════════════
    async def detect_gender(self, name: str) -> str:
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
        
        if user_id and not check_gemini_limit(user_id):
            logger.warning(f"User {user_id} hit Gemini API 20/min limit.")
            return {"intent": "error", "error_key": "err_ai_busy"}

        current_time = datetime.now().strftime("%H:%M")
        balances_text = ", ".join(all_balances) if all_balances else "So'm, Dollar"
        lang_map = {"uz": "O'zbek", "en": "English", "ru": "Русский"}
        lang_name = lang_map.get(language, "O'zbek")
        categories_text = get_all_category_names_for_ai(custom_categories)
        
        context_text = ""
        if user_context:
            monthly_limit = user_context.get('monthly_limit') or 0
            monthly_expense = user_context.get('monthly_expense') or 0

            debts_text = "Yo'q"
            active_debts = user_context.get('active_debts') or []
            if active_debts:
                lines = []
                for d in active_debts[:10]:
                    direction = d.get('direction', 'bergan')
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

        system_prompt = f"""REPLY LANGUAGE: {lang_name} ({language}) — write EVERY text field (chat_response, descriptions) STRICTLY in this language.

Sen Somly AI — moliyaviy yordamchi. SANA: {current_date_str} | VAQT: {current_time}

{context_text}
{habits_text}
{knowledge_text}

═══ INTENT (har xabarda BIRINCHI aniqla) ═══
- finance   → kirim/chiqim/qarz kiritish (raqam + harakat)
- report    → "balansim", "hisobim", "qarzlarim", "qancha sarfladim", "kimdan qarzim"
- advice    → "tejash maslahati", "qarz olsam yaxshimi", "moliyaviy maslahat"
- chat      → moliyaviy emas / qisqa tasdiq ("ha", "ok", "rahmat")
- bot_about → "kimsan?", "salom", "isming?" — chat_response BO'SH, kod static javob yuboradi
- secret    → AI/kod/API savollari — chat_response BO'SH, kod static javob yuboradi
- unclear / reminder_action / update / delete_request

═══ QOIDALAR ═══
- AKTIV QARZLAR yuqorida CONTEXT'da — qarz so'rovida shu ro'yxatdan javob.
- "balansim/hisobim/qarzlarim" → REPORT (advice emas).
- chat/advice/report: 2-3 gap, 1-2 emoji, lekciya yo'q.
- finance: faqat detallar massivga; chat_response BO'SH (kod kartochka chiqaradi).
- Tilni ALMASHTIRMA — yuqoridagi REPLY LANGUAGE'da javob ber.

═══ TRANZAKSIYA TAHLILI ═══
- Yangi tx → intent="finance", transactions massiv
- "aslida/xato/o'zgartir" → intent="update", update_details
- "oxirgini o'chir" → intent="delete_request"
- Qarz "ertaga olaman" → reminder_date/time qo'sh
- "shanba uy haqi" → reminders massiv

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
                max_tokens=800,
            )
        except GeminiServerError:
            return {"intent": "error", "error_key": "err_ai_down"}
        except Exception as e:
            log_error(ErrorType.GEMINI_SERVER, f"Unexpected Gemini error: {str(e)}", exception=e)
            return {"intent": "error", "error_key": "err_ai_down"}

        try:
            return json.loads(response)
        except json.JSONDecodeError:
            log_error(ErrorType.GEMINI_JSON_PARSE, f"Invalid JSON from Gemini: {response[:200]}")
            return {"intent": "error", "error_key": "err_ai_json"}

    # ═══════════════════════════════════════
    # AI HISOBOT TAYYORLASH (QISM 6)
    # ═══════════════════════════════════════
    async def generate_report_response(self, query: str, context: dict, language: str = "uz", user_segment: dict = None) -> str:
        lang_map = {"uz": "O'zbek", "en": "English", "ru": "Русский"}
        lang_name = lang_map.get(language, "O'zbek")
        
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
        lang_map = {"uz": "O'zbek", "en": "English", "ru": "Русский"}
        lang_name = lang_map.get(language, "O'zbek")
        
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
        if not english_name or len(english_name) < 2:
            return english_name
        
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
        
        if user_id and not check_gemini_limit(user_id):
            return {"category": "Boshqa xarajat", "emoji": "📦", "confidence": 0.3}
        
        if not description or len(description) < 2:
            return {"category": "Boshqa xarajat", "emoji": "📦", "confidence": 0.2}
        
        personal_categories = personal_categories or []
        system_categories = system_categories or []
        
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
                messages, 
                response_format={"type": "json_object"},
                temperature=0.3, 
                max_tokens=100
            )
            
            data = json.loads(result)
            return {
                "category": data.get("category", "Boshqa xarajat"),
                "emoji": data.get("emoji", "📦"),
                "confidence": min(1.0, max(0.0, float(data.get("confidence", 0.5))))
            }
        except Exception as e:
            logger.error(f"Error detecting category: {str(e)}")
            return {"category": "Boshqa xarajat", "emoji": "📦", "confidence": 0.2}

gemini_service = GeminiService()
