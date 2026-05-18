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
import itertools
from datetime import datetime
from typing import List, Dict, Any
from google import genai
from google.genai import types

from src.config import GEMINI_API_KEYS, GEMINI_MODEL, ADMIN_ID, BOT_TOKEN
from src.categories import get_all_category_names_for_ai
from src.services.error_handler import log_error, ErrorType
import aiohttp


def _try_repair_truncated_json(raw: str):
    """
    Uzilib qolgan JSON'ni qutqarish.
    Gemini max_tokens'da javobni kesib qo'ysa, oxiri buzilgan bo'ladi.
    Strategiya: birinchi `{` dan boshlab, brace balansini kuzatib boramiz
    va string ichida bo'lmagan oxirgi to'liq yopilgan `}` gacha kesamiz.
    """
    if not raw or not isinstance(raw, str):
        return None
    start = raw.find('{')
    if start < 0:
        return None
    depth = 0
    in_string = False
    escape = False
    last_complete = -1
    for i in range(start, len(raw)):
        ch = raw[i]
        if escape:
            escape = False
            continue
        if ch == '\\' and in_string:
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                last_complete = i
                break
    if last_complete < 0:
        return None
    candidate = raw[start:last_complete + 1]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return None


def _safe_extract_text(response) -> str:
    """
    Gemini response'dan matnni xavfsiz olish.
    Xavfsizlik filtri bloklasa yoki finish_reason != STOP bo'lsa,
    `response.text` ValueError chiqaradi — buni tutib aniq xabar beramiz.
    """
    try:
        return response.text
    except (ValueError, AttributeError):
        # Parts orqali tekshiramiz
        try:
            candidates = getattr(response, 'candidates', None) or []
            if candidates:
                parts = getattr(candidates[0].content, 'parts', None) or []
                texts = [getattr(p, 'text', '') for p in parts if hasattr(p, 'text')]
                if texts:
                    return ''.join(texts)
            # finish_reason — nima sabab
            reason = ''
            if candidates:
                reason = str(getattr(candidates[0], 'finish_reason', '')) or ''
            raise GeminiServerError(f"Empty response from Gemini (reason: {reason or 'unknown'})")
        except GeminiServerError:
            raise
        except Exception as e:
            raise GeminiServerError(f"Failed to extract Gemini text: {e}")

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

class GeminiAllKeysExhaustedError(Exception):
    """All Gemini API keys exhausted (quota/limit)."""
    pass

class GeminiQueueError(Exception):
    """Queue full — request should be retried later."""
    pass

# Backward-compat aliases — eski voice_handler/api kodlari uchun.
# Whisper Groq SDK'dan kelgan eski nomlar. Endi Gemini ishlatamiz, lekin
# kod tomondan import nomlarini buzmaslik uchun shu alias'larni saqlaymiz.
WhisperInvalidAudioError = GeminiInvalidAudioError
WhisperAllKeysExhaustedError = GeminiAllKeysExhaustedError


class GeminiService:
    def __init__(self):
        self.clients = []
        if not GEMINI_API_KEYS or len(GEMINI_API_KEYS) == 0:
            logger.error("GEMINI_API_KEYS is empty! Set GEMINI_API_KEY in .env")
        else:
            for key in GEMINI_API_KEYS:
                if key and not key.startswith("PUT_YOUR_"):
                    self.clients.append(genai.Client(api_key=key))
            
            if not self.clients:
                logger.error("No valid GEMINI_API_KEY found!")
            else:
                logger.info(f"GeminiService initialized with {len(self.clients)} keys")
                
        self.client_cycle = itertools.cycle(self.clients) if self.clients else None
        self.active_model = GEMINI_MODEL or "gemini-2.5-flash"
        
        self.safe_settings = [
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH, threshold=types.HarmBlockThreshold.BLOCK_NONE),
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HARASSMENT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
        ]

    @property
    def keys_stats(self):
        # Dummy stats to prevent scheduler crash
        class DummyStat:
            def __init__(self, idx):
                self.index = idx
                self.status = "active"
                self.requests_count = 0
                self.last_error_time = 0
                self.connection_errors = 0
        return [DummyStat(i) for i in range(len(self.clients))]

    def get_best_key(self):
        class DummyKey:
            def __init__(self, client):
                self.client = client
        
        if not self.clients:
            raise GeminiServerError("No clients available")
        return DummyKey(self.clients[0])

    def _get_next_client(self):
        if not self.client_cycle:
            return None
        return next(self.client_cycle)

    async def validate_keys_on_startup(self):
        """Test API key at startup."""
        if not self.clients:
            logger.error("WARNING: GEMINI_API_KEY missing or placeholder! All requests will fail.")
            await self.alert_admin("🚨 GEMINI_API_KEY .env faylida topilmadi yoki placeholder qiymat turibdi!")
            return

        valid_keys = 0
        for i in range(len(self.clients)):
            client = self._get_next_client()
            try:
                await asyncio.to_thread(
                    client.models.generate_content,
                    model=self.active_model,
                    contents="hi",
                    config=types.GenerateContentConfig(safety_settings=self.safe_settings)
                )
                valid_keys += 1
            except Exception as e:
                logger.warning(f"Validation error for a key: {e}")
        
        if valid_keys > 0:
            logger.info(f"Gemini API Keys: {valid_keys} VALID keys")
        else:
            await self.alert_admin(f"🚨 Barcha Gemini API kalitlari ishlamayapti yoki limitdan o'tgan!")

    async def alert_admin(self, message: str):
        try:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
            async with aiohttp.ClientSession() as session:
                await session.post(url, json={"chat_id": ADMIN_ID, "text": message})
        except Exception as e:
            logger.error(f"Failed to send admin alert: {e}")

    def _convert_messages_to_gemini(self, messages: List[Dict]) -> tuple:
        system_parts = []
        history = []
        for msg in messages:
            role = msg.get("role")
            content = msg.get("content", "") or ""
            if role == "system":
                system_parts.append(content)
            elif role == "user":
                history.append(types.Content(role="user", parts=[types.Part.from_text(text=content)]))
            elif role == "assistant":
                history.append(types.Content(role="model", parts=[types.Part.from_text(text=content)]))
        system_instruction = "\n\n".join(system_parts) if system_parts else None
        return system_instruction, history

    async def chat_completion_with_retry(self, messages: List[Dict], **kwargs) -> str:
        if not self.clients:
            raise GeminiServerError("Gemini Client not initialized")
            
        system_instruction, history = self._convert_messages_to_gemini(messages)

        config_dict = {"safety_settings": self.safe_settings}
        if system_instruction:
            config_dict["system_instruction"] = system_instruction
        if kwargs.get("temperature") is not None:
            config_dict["temperature"] = kwargs["temperature"]
        if kwargs.get("max_tokens") is not None:
            config_dict["max_output_tokens"] = kwargs["max_tokens"]
            
        response_format = kwargs.get("response_format")
        if response_format and response_format.get("type") == "json_object":
            config_dict["response_mime_type"] = "application/json"

        if not history:
            prompt = ""
        else:
            prompt_content = history[-1]
            if hasattr(prompt_content, "parts") and len(prompt_content.parts) > 0:
                prompt = prompt_content.parts[0].text
            else:
                prompt = ""
            history = history[:-1]

        # Free Tier 5 req/min => bitta kalit kvotasi 12 sekundda yangilanadi.
        # 1 kalit bo'lsa ham, 429 dan keyin kutib qayta urinamiz.
        BACKOFF_SECONDS = [13, 20]  # MAX_CYCLES = 1 + len(BACKOFF_SECONDS) = 3
        last_exception = None
        n_clients = max(1, len(self.clients))

        for cycle, wait_before in enumerate([0, *BACKOFF_SECONDS]):
            if wait_before:
                logger.warning(
                    f"All {n_clients} key(s) rate limited. Sleeping {wait_before}s before retry cycle {cycle+1}."
                )
                await asyncio.sleep(wait_before)

            for _ in range(n_clients):
                client = self._get_next_client()
                try:
                    if history:
                        chat = client.chats.create(
                            model=self.active_model,
                            config=types.GenerateContentConfig(**config_dict),
                            history=history
                        )
                        response = await asyncio.to_thread(chat.send_message, prompt)
                    else:
                        response = await asyncio.to_thread(
                            client.models.generate_content,
                            model=self.active_model,
                            contents=prompt,
                            config=types.GenerateContentConfig(**config_dict)
                        )

                    return _safe_extract_text(response)
                except Exception as e:
                    err_str = str(e)
                    if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                        logger.warning(f"Key rate limited (429). Cycle {cycle+1}. Error: {e}")
                        last_exception = e
                        continue
                    else:
                        logger.error(f"Gemini API Error: {e}")
                        raise GeminiServerError(f"Gemini Error: {e}")

        raise GeminiAllKeysExhaustedError(f"All keys exhausted after retries. Last error: {last_exception}")

    async def stream_chat_completion_with_retry(self, messages: List[Dict], **kwargs):
        if not self.clients:
            yield "Xatolik: Tizim sozlanmagan."
            return
            
        system_instruction, history = self._convert_messages_to_gemini(messages)
        
        config_dict = {"safety_settings": self.safe_settings}
        if system_instruction:
            config_dict["system_instruction"] = system_instruction
            
        if not history:
            yield "Xatolik: Matn kiritilmadi."
            return
            
        prompt_content = history[-1]
        if hasattr(prompt_content, "parts") and len(prompt_content.parts) > 0:
            prompt = prompt_content.parts[0].text
        else:
            prompt = ""
        history = history[:-1]

        # Streaming does not retry easily due to generator nature, so we just pick the next client once.
        client = self._get_next_client()
        try:
            if history:
                chat = client.chats.create(
                    model=self.active_model,
                    config=types.GenerateContentConfig(**config_dict),
                    history=history
                )
                response_stream = await asyncio.to_thread(chat.send_message_stream, prompt)
            else:
                response_stream = await asyncio.to_thread(
                    client.models.generate_content_stream,
                    model=self.active_model,
                    contents=prompt,
                    config=types.GenerateContentConfig(**config_dict)
                )

            iterator = iter(response_stream)
            sentinel = object()
            while True:
                chunk = await asyncio.to_thread(next, iterator, sentinel)
                if chunk is sentinel:
                    break
                try:
                    text = chunk.text
                except (ValueError, AttributeError):
                    text = None
                if text:
                    yield text
        except Exception as e:
            logger.error(f"Gemini Stream Error: {e}")
            yield "Xatolik: Tizim hozircha javob bera olmaydi."

    async def transcribe_audio_with_retry(self, file_path: str) -> str:
        if not os.path.exists(file_path):
            raise GeminiInvalidAudioError(f"Audio file missing: {file_path}")

        file_size = os.path.getsize(file_path)
        fname = os.path.basename(file_path)
        
        if file_size == 0:
            raise GeminiInvalidAudioError(f"Audio file empty: {file_path}")

        if not self.clients:
            raise GeminiServerError("Gemini Client not initialized")

        prompt = "Iltimos, ushbu audioni diqqat bilan eshitib, so'zma-so'z matnga o'giring. Faqat eshitilgan matnni yozing, izoh yoki boshqa narsa qo'shmang."
        ext = fname.rsplit('.', 1)[-1].lower() if '.' in fname else 'ogg'
        mime_map = {'ogg': 'audio/ogg', 'oga': 'audio/ogg', 'mp3': 'audio/mpeg',
                    'wav': 'audio/wav', 'm4a': 'audio/mp4', 'mp4': 'audio/mp4',
                    'webm': 'audio/webm', 'flac': 'audio/flac'}
        mime_type = mime_map.get(ext, 'audio/ogg')
        INLINE_LIMIT = 20 * 1024 * 1024

        # Bitta kalit holatda ham 429 ushlansa biroz kutib qayta urinamiz.
        BACKOFF_SECONDS = [13, 20]
        last_exception = None
        n_clients = max(1, len(self.clients))

        for cycle, wait_before in enumerate([0, *BACKOFF_SECONDS]):
            if wait_before:
                logger.warning(
                    f"Audio: all {n_clients} key(s) rate limited. Sleeping {wait_before}s before retry cycle {cycle+1}."
                )
                await asyncio.sleep(wait_before)

            for _ in range(n_clients):
                client = self._get_next_client()
                myfile = None
                try:
                    if file_size <= INLINE_LIMIT:
                        with open(file_path, 'rb') as f:
                            audio_bytes = f.read()

                        response = await asyncio.to_thread(
                            client.models.generate_content,
                            model=self.active_model,
                            contents=[types.Part.from_bytes(data=audio_bytes, mime_type=mime_type), prompt],
                            config=types.GenerateContentConfig(safety_settings=self.safe_settings)
                        )
                    else:
                        myfile = await asyncio.to_thread(client.files.upload, file=file_path)
                        response = await asyncio.to_thread(
                            client.models.generate_content,
                            model=self.active_model,
                            contents=[myfile, prompt],
                            config=types.GenerateContentConfig(safety_settings=self.safe_settings)
                        )

                    return _safe_extract_text(response).strip()
                except Exception as e:
                    err_str = str(e)
                    if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                        logger.warning(f"Audio rate limited (429). Cycle {cycle+1}. Error: {e}")
                        last_exception = e
                        continue
                    else:
                        logger.error(f"Gemini Audio error: {e}")
                        raise GeminiServerError(f"Audio processing error: {e}")
                finally:
                    if myfile is not None:
                        try:
                            await asyncio.to_thread(client.files.delete, name=myfile.name)
                        except Exception:
                            pass

        raise GeminiAllKeysExhaustedError(f"All keys exhausted for audio after retries. Last error: {last_exception}")

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
                max_tokens=1500,
            )
        except GeminiAllKeysExhaustedError:
            # Inner retry+backoff tugadi. Yana kutkazmaymiz — foydalanuvchi qayta yuborsin.
            return {"intent": "error", "error_key": "err_ai_busy"}
        except GeminiServerError:
            return {"intent": "error", "error_key": "err_ai_down"}
        except Exception as e:
            log_error(ErrorType.GEMINI_SERVER, f"Unexpected Gemini error: {str(e)}", exception=e)
            return {"intent": "error", "error_key": "err_ai_down"}

        try:
            return json.loads(response)
        except json.JSONDecodeError:
            # Truncated JSON repair — agar javob max_tokens'da uzilib qolgan bo'lsa,
            # oxirgi to'liq yopilgan } gacha kesib, qayta urinib ko'ramiz.
            repaired = _try_repair_truncated_json(response)
            if repaired is not None:
                logger.warning("Recovered truncated JSON from Gemini response")
                return repaired
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
