"""
Message handler — core of the bot.
Processes text messages through AI and saves transactions/debts.

Error handling:
- AI returns error intent → show user-friendly message
- Duplicate messages → silently ignored
- DB errors → catch, log, alert admin
- MongoDB connection errors → friendly message + admin alert
"""

import asyncio
import logging
from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo, CallbackQuery
from aiogram.fsm.context import FSMContext
from src.database import (
    insert_transaction, insert_debt,
    update_user_balance, get_user_balance,
    get_monthly_expense, get_user, ensure_balance_exists,
    get_user_financial_context, get_recent_transactions_context,
    get_user_habits,
    get_last_transaction, delete_transaction_by_id, update_transaction_by_id, get_monthly_summary,
    get_webapp_url, get_user_all_balance_names, get_custom_categories,
    get_chat_history, save_chat_message, reminders_collection,
    get_user_all_balances,
)
from src.services.groq_service import groq_service, GroqQueueError
from src.services.scheduler import schedule_one_time_reminder
from src.services.i18n import t
from src.services.error_handler import (
    log_error, handle_error, ErrorType,
    is_duplicate_message
)
from src.states import TransactionAmbiguity

logger = logging.getLogger(__name__)
router = Router()


async def build_webapp_keyboard(page: str = "/", lang: str = "uz", button_text: str = None) -> InlineKeyboardMarkup:
    """Build inline keyboard with Mini App deep-link button."""
    url = await get_webapp_url()
    full_url = f"{url}#{page}" if page != "/" else url
    text = button_text or t(lang, "view_in_miniapp")
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=text, web_app=WebAppInfo(url=full_url))]
    ])




def format_number(num: float) -> str:
    """1234567 → '1 234 567'"""
    if num < 0:
        return "-" + f"{int(abs(num)):,}".replace(",", " ")
    return f"{int(num):,}".replace(",", " ")


def parse_display_date(date_str: str) -> str:
    """YYYY-MM-DD → DD.MM.YYYY"""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%d.%m.%Y")
    except Exception:
        return date_str


async def build_fallback_balance_text(user_id: int) -> str:
    """
    Build a balance summary directly from MongoDB (no AI).
    Used when AI is unavailable but user asked for balance info.
    """
    try:
        balances = await get_user_all_balances(user_id)
    except Exception as e:
        logger.error(f"Fallback balance: failed to fetch for {user_id}: {e}")
        return "💰 Hozir balans ma'lumotlarini olib bo'lmadi. Keyinroq urinib ko'ring."

    if not balances:
        return "💰 Sizda hali balans yo'q. /newbalance bilan qo'shing."

    lines = ["💰 Sizning balansingiz:"]
    for currency, info in balances.items():
        amount = info.get("amount", 0)
        title = info.get("title", currency)
        lines.append(f"• {title}: {format_number(amount)} {currency}")
    return "\n".join(lines)


async def check_limit_warning(telegram_id: int, currency: str, new_expense_total: float, lang: str = "uz") -> str:
    """
    Limitni tekshirish.
    Returns warning string or empty string.
    """
    user = await get_user(telegram_id)
    bal_info = user.get("balances", {}).get(currency, {})
    limit = bal_info.get("limit")

    if not limit or limit <= 0:
        return ""

    pct = new_expense_total / limit

    if pct >= 1.0:
        return t(lang, "limit_warning_danger")
    elif pct >= 0.8:
        return t(lang, "limit_warning_alert", spent=f"{format_number(new_expense_total)} {currency}")
    else:
        return ""


def build_debt_keyboard(debt_id: str, lang: str = "uz") -> InlineKeyboardMarkup:
    """Qarz uchun inline tugmalar."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=t(lang, "debt_btn_pay"), callback_data=f"debt_paid:{debt_id}"),
            InlineKeyboardButton(text=t(lang, "debt_btn_del"), callback_data=f"debt_delete:{debt_id}"),
        ]
    ])


async def build_debt_webapp_keyboard(debt_id: str, lang: str = "uz") -> InlineKeyboardMarkup:
    """Qarz saqlanganda: inline tugmalar + Mini App deep link."""
    url = await get_webapp_url()
    full_url = f"{url}#/debts"
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=t(lang, "debt_btn_pay"), callback_data=f"debt_paid:{debt_id}"),
            InlineKeyboardButton(text=t(lang, "debt_btn_del"), callback_data=f"debt_delete:{debt_id}"),
        ],
        [
            InlineKeyboardButton(text="💸 " + t(lang, "deeplink_view_debts"), web_app=WebAppInfo(url=full_url))
        ]
    ])


def build_tx_inline_keyboard(tx_id: str, lang: str = "uz") -> InlineKeyboardMarkup:
    """Tranzaksiya uchun asosiy inline amallar."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Kategoriyani o'zgartirish", callback_data=f"edit_cat:{tx_id}:0")],
        [InlineKeyboardButton(text="💳 Hisobni o'zgartirish", callback_data=f"edit_bal:{tx_id}")],
        [InlineKeyboardButton(text="🗑 O'chirish", callback_data=f"del_tx:{tx_id}")]
    ])


def build_category_selector_keyboard(tx_id: str, page: int = 0, lang: str = "uz") -> InlineKeyboardMarkup:
    """Kategoriyalarni tanlash (paginated)."""
    from src.categories import SYSTEM_CATEGORIES
    per_page = 15
    start = page * per_page
    end = start + per_page
    
    cats = SYSTEM_CATEGORIES[start:end]
    buttons = []
    
    # 3 ta ustunli tugmalar
    for i in range(0, len(cats), 3):
        row = []
        for cat in cats[i:i+3]:
            # Callback data: set_cat:{tx_id}:{cat_name}
            # Note: cat_name might be long, but we need it. 
            # Better to use index or shorter ID if possible, but cat name is unique enough here.
            row.append(InlineKeyboardButton(text=f"{cat['emoji']} {cat['name']}", callback_data=f"set_cat:{tx_id}:{cat['name'][:20]}"))
        buttons.append(row)
        
    # Navigatsiya
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="⬅️", callback_data=f"edit_cat:{tx_id}:{page-1}"))
    if end < len(SYSTEM_CATEGORIES):
        nav_row.append(InlineKeyboardButton(text="➡️", callback_data=f"edit_cat:{tx_id}:{page+1}"))
    if nav_row:
        buttons.append(nav_row)
        
    buttons.append([InlineKeyboardButton(text="🔙 Orqaga", callback_data=f"tx_back:{tx_id}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def build_balance_selector_keyboard(tx_id: str, user_id: int, lang: str = "uz") -> InlineKeyboardMarkup:
    """Balanslarni (hisoblarni) tanlash."""
    from src.database import get_user_all_balances
    balances = await get_user_all_balances(user_id)
    
    buttons = []
    for code, info in balances.items():
        title = info.get("title", code)
        amt = info.get("amount", 0)
        buttons.append([InlineKeyboardButton(
            text=f"{title} ({format_number(amt)})", 
            callback_data=f"set_bal:{tx_id}:{code}"
        )])
        
    buttons.append([InlineKeyboardButton(text="🔙 Orqaga", callback_data=f"tx_back:{tx_id}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_delete_confirm_keyboard(tx_id: str, lang: str = "uz") -> InlineKeyboardMarkup:
    """O'chirishni tasdiqlash tugmalari."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Ha", callback_data=f"confirm_del:{tx_id}"),
            InlineKeyboardButton(text="❌ Bekor", callback_data=f"tx_back:{tx_id}")
        ]
    ])


def build_reminder_keyboard(reminder_id: str, lang: str = "uz") -> InlineKeyboardMarkup:
    """Eslatma yuborilganda chiqadigan tugmalar."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ " + t(lang, "rem_done"), callback_data=f"rem_done:{reminder_id}"),
            InlineKeyboardButton(text="⏰ " + t(lang, "rem_later"), callback_data=f"rem_later:{reminder_id}"),
        ],
        [
            InlineKeyboardButton(text="❌ " + t(lang, "rem_cancel"), callback_data=f"rem_cancel:{reminder_id}"),
        ]
    ])


async def process_reminders(user_id: int, reminders: list, related_debt_id: str = None):
    """AI dan kelgan eslatmalarni bazaga saqlash."""
    from src.database import insert_reminder
    from datetime import datetime
    
    for r in reminders:
        time_str = r.get("time")
        if not time_str: continue
        
        try:
            scheduled_time = datetime.strptime(time_str, "%Y-%m-%d %H:%M")
        except (ValueError, TypeError):
            logger.warning(f"Failed to parse reminder time: {time_str}")
            continue
            
        await insert_reminder({
            "user_id": user_id,
            "type": r.get("type", "general"),
            "message": r.get("message", ""),
            "scheduled_time": scheduled_time,
            "related_debt_id": related_debt_id,
            "status": "pending"
        })


@router.message(F.text)
async def process_text_message(message: Message, state: FSMContext):
    await handle_transaction_text(message, message.text, state)


async def handle_transaction_text(message: Message, text: str, state: FSMContext = None):
    """
    Main processing pipeline:
    1. Duplicate check
    2. Typing indicator (user darhol bot ishlayotganini his qiladi)
    3. Context fetch & AI parse
    4. Ambiguity resolution (FSM)
    5. Handle error intents & chat
    6. Save & respond with formatted message
    """
    # ── Defensive lokal binding (UnboundLocalError oldini olish) ──
    from src.services.groq_service import groq_service as _gs
    groq_service = _gs

    user_id = message.from_user.id
    current_date = datetime.now().strftime("%Y-%m-%d")

    # ─── 0. Duplicate check ───
    if is_duplicate_message(user_id, text):
        logger.info(f"Duplicate message ignored from {user_id}: {text[:50]}")
        return

    # ─── 0.5. Typing indicator — foydalanuvchi darhol "yozmoqda..." his qiladi ───
    # Fire-and-forget: blokirovka qilmaydi, xato bo'lsa indikator ko'rinmaydi
    async def _send_typing():
        try:
            await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
        except Exception:
            pass
    asyncio.create_task(_send_typing())

    user = await get_user(user_id)
    language = user.get("language", "uz")

    # Fetch context — parallel for speed
    custom_cats, user_context, recent_txs, habits, all_balance_names, chat_history = await asyncio.gather(
        get_custom_categories(user_id),
        get_user_financial_context(user_id),
        get_recent_transactions_context(user_id),
        get_user_habits(user_id),
        get_user_all_balance_names(user_id),
        get_chat_history(user_id),
    )
    custom_cats_list = [{"emoji": c["emoji"], "name": c["name"], "type": c["type"]} for c in custom_cats] if custom_cats else None
    
    # Save user message to history (fire-and-forget)
    asyncio.create_task(save_chat_message(user_id, "user", text))

    # ─── 1. Send to AI ───
    status_msg = None  # "Bir daqiqa..." xabar reference (edit/delete uchun)
    try:
        data = await groq_service.parse_transaction(
            text=text,
            current_date_str=current_date,
            language=language,
            custom_categories=custom_cats_list,
            user_id=user_id,
            user_context=user_context,
            recent_txs=recent_txs,
            habits=habits,
            all_balances=all_balance_names,
            chat_history=chat_history
        )
    except GroqQueueError:
        # Status xabar yuboramiz va reference saqlaymiz — edit/delete uchun
        try:
            status_msg = await message.answer("⏳")
        except Exception:
            status_msg = None
        asyncio.create_task(handle_queued_transaction(
            message, text, current_date, language, custom_cats_list, user_id,
            user_context, recent_txs, habits, state, all_balance_names, chat_history,
            status_msg=status_msg,
        ))
        return
    except Exception as e:
        log_error(ErrorType.GROQ_SERVER, f"Unexpected AI error", user_id, e)
        await message.answer(t(language, "err_ai_down"))
        return

    await process_parsed_data(data, message, user_id, language, current_date, custom_cats, state, habits)


async def handle_queued_transaction(
    message, text, current_date, language, custom_cats_list, user_id,
    user_context, recent_txs, habits, state, all_balance_names=None,
    chat_history=None, status_msg=None,
):
    """
    Retry parse_transaction with bounded attempts.
    Max ~15s total: 3 attempts × 5s. Foydalanuvchini cheksiz kutkazmaymiz.
    Status xabar har urinishda yangilanadi.
    """
    # ── Defensive lokal binding ──
    from src.services.groq_service import groq_service as _gs
    groq_service = _gs

    MAX_ATTEMPTS = 3
    RETRY_DELAY = 5  # 30s → 5s: kalitlar cooling 60s, lekin har 5s da yangisini probe qilamiz

    async def update_status(text_):
        if status_msg is None:
            return
        try:
            await status_msg.edit_text(text_)
        except Exception:
            pass

    async def delete_status():
        if status_msg is None:
            return
        try:
            await status_msg.delete()
        except Exception:
            pass

    data = None
    last_exc = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            data = await groq_service.parse_transaction(
                text=text,
                current_date_str=current_date,
                language=language,
                custom_categories=custom_cats_list,
                user_id=user_id,
                user_context=user_context,
                recent_txs=recent_txs,
                habits=habits,
                all_balances=all_balance_names,
                chat_history=chat_history
            )
            break  # muvaffaqiyat
        except GroqQueueError as e:
            last_exc = e
            if attempt < MAX_ATTEMPTS:
                await update_status(t(language, "ai_busy_short", n=attempt, total=MAX_ATTEMPTS))
                await asyncio.sleep(RETRY_DELAY)
            else:
                # Barcha urinishlar tugadi
                await update_status(t(language, "err_ai_busy"))
                return
        except Exception as e:
            log_error(ErrorType.GROQ_SERVER, f"Unexpected AI error in queue (attempt {attempt})", user_id, e)
            await update_status(t(language, "err_ai_down"))
            return

    # Muvaffaqiyat — status xabarni o'chiramiz (real javob keladi)
    await delete_status()

    if data is None:
        # Bu yerga kelmasligi kerak, lekin xavfsizlik uchun
        try:
            await message.answer(t(language, "err_ai_down"))
        except Exception:
            pass
        return

    await process_parsed_data(data, message, user_id, language, current_date, custom_cats_list, state, habits)
async def process_parsed_data(data: dict, message: Message, user_id: int, language: str, current_date: str, custom_cats: list, state: FSMContext, habits: dict = None):
    # ── Defensive: lokal binding ──
    # Python scoping zaifligi: agar funksiya ichida BIROR JOYDA `groq_service = ...`
    # yoki `from src.services.groq_service import groq_service` bo'lsa,
    # butun funksiyada top-level import "ko'rinmas" bo'lib qoladi va
    # UnboundLocalError keladi. Shuning uchun shu yerda MAJBURIY rebind qilamiz.
    from src.services.groq_service import groq_service as _gs
    groq_service = _gs

    intent = data.get("intent")

    # ─── 4. General Reminders ───
    ai_reminders = data.get("reminders", [])
    if ai_reminders:
        await process_reminders(user_id, ai_reminders)

    # ─── 1.5. Handle error intent from AI ───
    if intent == "error":
        error_key = data.get("error_key")
        # LLM o'zi 'error' qaytarib error_key bermagan bo'lsa (hallucination), unclear ga o'tkazamiz
        if not error_key or error_key == "err_general":
            error_key = "err_unclear_input"
            
        error_msg = t(language, error_key)
        
        if error_key == "err_unclear_input":
            kb = await build_webapp_keyboard("/", language)
            await message.answer(error_msg, reply_markup=kb)
        else:
            await message.answer(error_msg)
        return

    # ─── AQLLI MASLAHAT (Advice Intent) ───
    if intent == "advice":
        from src.database import get_financial_advice_context, get_user

        await message.answer(t(language, "ai_thinking"))

        try:
            user_data = await get_user(user_id)
            currency = "UZS"
            context_data = await get_financial_advice_context(user_id, currency)

            advice_text = await groq_service.generate_smart_financial_advice(
                user_context=user_data,
                financial_data=context_data,
                trigger_type="user_requested",
                language=language
            )
            await message.answer(advice_text)
        except GroqQueueError:
            await message.answer(t(language, "err_ai_busy"))
        except Exception as e:
            log_error(ErrorType.GROQ_SERVER, f"Advice generation failed", user_id, e)
            # Fallback: send a chat_response if AI provided one, else a generic message
            fallback = data.get("chat_response") or t(language, "ai_advice_fallback")
            await message.answer(fallback)
        return

    # ─── 1.6. Special Intents (QISM 6) ───
    if intent == "delete_request":
        url = await get_webapp_url()
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📱 " + t(language, "deeplink_view_debts"), web_app=WebAppInfo(url=f"{url}#/"))]])
        reply_msg = "Mini ilovaga kirib keraksiz qismni o'chirib tashlashingiz mumkin 👇"
        await message.answer(reply_msg, reply_markup=kb)
        await save_chat_message(user_id, "assistant", reply_msg)
        return
        
    if intent == "update":
        update_details = data.get("update_details", {})
        target_id = update_details.get("target_id", "")
        new_values = update_details.get("new_values", {})
        reply_msg = "❌ Tahrirlash uchun ma'lumot topilmadi."
        
        if target_id and new_values:
            from bson import ObjectId
            try:
                if target_id.startswith("TX_ID: "):
                    actual_id = target_id.replace("TX_ID: ", "").strip()
                    success = await update_transaction_by_id(actual_id, new_values)
                    if success:
                        reply_msg = "✅ Tranzaksiya muvaffaqiyatli yangilandi!"
                elif target_id.startswith("DEBT_ID: "):
                    actual_id = target_id.replace("DEBT_ID: ", "").strip()
                    from src.database import debts_collection
                    await debts_collection.update_one({"_id": ObjectId(actual_id)}, {"$set": new_values})
                    reply_msg = "✅ Qarz yozuvi muvaffaqiyatli yangilandi!"
            except Exception as e:
                logger.error(f"Update error: {e}")
                
        await message.answer(reply_msg)
        await save_chat_message(user_id, "assistant", reply_msg)
        return

    if intent == "reminder_action":
        from src.database import reminders_collection, update_reminder_status
        last_rem = await reminders_collection.find_one(
            {"user_id": user_id, "status": {"$in": ["reminded", "pending"]}},
            sort=[("scheduled_time", -1)]
        )
        if last_rem:
            text_lower = (message.text or "").lower()
            if any(x in text_lower for x in ["bajar", "oldim", "qildim", "yop"]):
                await update_reminder_status(str(last_rem["_id"]), "done")
                await message.answer("✅ Eslatma bajarildi deb belgilandi.")
            elif any(x in text_lower for x in ["bekor", "o'chir", "yo'qot"]):
                await update_reminder_status(str(last_rem["_id"]), "cancelled")
                await message.answer("❌ Eslatma bekor qilindi.")
            else:
                # Yangi vaqtga qoldirilgan bo'lsa (AI 'reminders' qaytargan bo'ladi)
                await update_reminder_status(str(last_rem["_id"]), "done")
                await message.answer(data.get("chat_response") or "Xo'p bo'ladi, tushundim!")
        else:
            await message.answer(data.get("chat_response") or "Tushundim!")
        return
        
    if intent == "report":
        from src.database import get_report_context
        query = data.get("report_query", "qancha sarfladim?")

        try:
            context = await get_report_context(user_id)
            user_segment = data.get("user_segment")
            report_text = await groq_service.generate_report_response(query, context, language, user_segment)
            kb = await build_webapp_keyboard("/reports", language, button_text="📊 " + t(language, "deeplink_view_reports"))
            await message.answer(report_text, reply_markup=kb)
        except GroqQueueError:
            # AI band — direct balansni qaytaramiz
            fallback = await build_fallback_balance_text(user_id)
            kb = await build_webapp_keyboard("/reports", language, button_text="📊 " + t(language, "deeplink_view_reports"))
            await message.answer(fallback, reply_markup=kb)
        except Exception as e:
            log_error(ErrorType.GROQ_SERVER, f"Report generation failed", user_id, e)
            # MongoDB yoki AI xato — fallback ravishda balansni DIRECT yuboramiz
            fallback = await build_fallback_balance_text(user_id)
            try:
                kb = await build_webapp_keyboard("/reports", language, button_text="📊 " + t(language, "deeplink_view_reports"))
                await message.answer(fallback, reply_markup=kb)
            except Exception:
                await message.answer(fallback)
        return

    # ─── 2. Bot haqida savol (o'zini tanishtirish) ───
    # Static javob — i18n orqali user tilida. AI promptga shu matnni bermaymiz (token tejash).
    if intent == "bot_about":
        reply_msg = t(language, "bot_intro")
        url = await get_webapp_url()
        base_url = url.rstrip('/') if url else ""
        privacy_url = f"{base_url}/#/privacy" if base_url else ""
        buttons = []
        if privacy_url:
            buttons.append([InlineKeyboardButton(text=t(language, "btn_privacy"), web_app=WebAppInfo(url=privacy_url))])
        buttons.append([InlineKeyboardButton(text=t(language, "btn_open_miniapp"), web_app=WebAppInfo(url=url))])
        kb = InlineKeyboardMarkup(inline_keyboard=buttons)
        await message.answer(reply_msg, reply_markup=kb)
        await save_chat_message(user_id, "assistant", reply_msg)
        return

    # ─── 3. Maxfiy savol (himoya) ───
    # Static javob — i18n orqali user tilida.
    if intent == "secret":
        reply_msg = t(language, "bot_secret_reply")
        await message.answer(reply_msg)
        await save_chat_message(user_id, "assistant", reply_msg)
        return

    # ─── 4. Chat yoki Advice intent ───
    if intent in ["chat", "advice"]:
        reply_msg = data.get("chat_response") or data.get("reply", "...")
        await message.answer(reply_msg)
        await save_chat_message(user_id, "assistant", reply_msg)
        return

    # ─── 3. Unclear / Ambiguity Protocol ───
    if data.get("unclear"):
        reason = data.get("unclear_reason", "")
        extracted_tx = data.get("transactions", [{}])[0] if data.get("transactions") else {}
        
        # Check strike counter
        current_state_data = await state.get_data() if state else {}
        strikes = current_state_data.get("unclear_strikes", 0) + 1
        
        if strikes >= 3:
            await message.answer("Tushunmadim. Iltimos aniqroq yozing. Masalan: 'Taksiga 15 ming so'm to'ladim'.")
            if state: await state.clear()
            return
            
        if state:
            await state.update_data(unclear_strikes=strikes, partial_tx=extracted_tx)
            
        if reason == "missing_amount":
            await message.answer("Qancha? Miqdorni aytmadingiz.")
            if state: await state.set_state(TransactionAmbiguity.waiting_for_amount)
            return
        elif reason == "missing_type":
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="💰 Kirim", callback_data="resolve_type:kirim"),
                    InlineKeyboardButton(text="💸 Chiqim", callback_data="resolve_type:chiqim")
                ]
            ])
            await message.answer("Bu kirimmi yoki chiqim?", reply_markup=kb)
            if state: await state.set_state(TransactionAmbiguity.waiting_for_type)
            return
        elif reason == "missing_debt_date":
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="📅 Muddat belgilash", callback_data="resolve_date:set"),
                    InlineKeyboardButton(text="⏭ Muddat yo'q", callback_data="resolve_date:skip")
                ]
            ])
            await message.answer("Qachon qaytaradi?", reply_markup=kb)
            if state: await state.set_state(TransactionAmbiguity.waiting_for_debt_date)
            return
        else:
            await message.answer(t(language, "voice_not_understood"))
            return

    # ─── 4. Process transactions ───
    if state: await state.clear()
    
    transactions = data.get("transactions", [])
    ai_reply = data.get("chat_response") or data.get("reply", t(language, "tx_saved"))
    tip = data.get("tip")

    if not transactions and ai_reminders:
        reply_msg = ai_reply if ai_reply else "✅ Eslatma muvaffaqiyatli saqlandi!"
        if tip:
            reply_msg += f"\n\n💡 {tip}"
        await message.answer(reply_msg)
        return
        
    await process_extracted_transactions(message, transactions, user_id, language, current_date, custom_cats, ai_reply, habits, state, tip)

async def enhance_category_with_ai(description: str, original_category: str, personal_cats: list, user_id: int, tx_type: str = "chiqim") -> tuple:
    # ── Defensive lokal binding ──
    from src.services.groq_service import groq_service as _gs
    groq_service = _gs

    """
    Enhance category detection using AI.
    Returns: (category, confidence)
    
    If AI confidence > 0.6, uses AI-detected category.
    If the detected category is new, it is saved as a personal category.
    Otherwise uses original category.
    """
    try:
        from src.categories import SYSTEM_CATEGORIES
        from src.database import add_custom_category
        import re

        def clean_name(value: str) -> str:
            value = (value or "").strip()
            return re.sub(r"^[^\w']+\s*", "", value).strip()

        def norm(value: str) -> str:
            return clean_name(value).lower()

        def find_existing(name: str):
            name_norm = norm(name)
            allowed_types = {tx_type, "both"} if tx_type in ["kirim", "chiqim"] else {"kirim", "chiqim", "both"}
            for cat in personal_cats or []:
                if norm(cat.get("name")) == name_norm and cat.get("type") in allowed_types:
                    return cat
            for cat in SYSTEM_CATEGORIES:
                if norm(cat.get("name")) == name_norm and cat.get("type") in allowed_types:
                    return cat
            return None

        def force_product_category(result: dict) -> dict:
            desc = (description or "").lower()
            category_name = norm(result.get("category"))
            flower_words = ["gul", "gullar", "guldasta", "atirgul", "lola", "flower", "flowers", "florist"]
            if any(word in desc for word in flower_words) and category_name != "gullar":
                return {"category": "Gullar", "emoji": "🌸", "confidence": 0.95, "is_new": True}
            return result
        
        # Call AI detection
        result = await groq_service.detect_category_for_transaction(
            description=description,
            personal_categories=personal_cats,
            system_categories=SYSTEM_CATEGORIES,
            user_id=user_id
        )
        result = force_product_category(result)
        
        ai_confidence = result.get("confidence", 0.3)
        ai_category = clean_name(result.get("category", original_category))
        ai_emoji = result.get("emoji", "📦")
        existing = find_existing(ai_category)
        is_new = existing is None
        
        # Use AI result only if confidence > 0.6
        if ai_confidence > 0.6:
            if is_new:
                cat_type = tx_type if tx_type in ["kirim", "chiqim"] else "chiqim"
                if not any(norm(c.get("name")) == norm(ai_category) and c.get("type") in [cat_type, "both"] for c in personal_cats or []):
                    await add_custom_category(user_id, ai_emoji, ai_category, cat_type)
                    if isinstance(personal_cats, list):
                        personal_cats.append({"emoji": ai_emoji, "name": ai_category, "type": cat_type})
                return f"{ai_emoji} {ai_category}", ai_confidence

            return f"{existing.get('emoji', ai_emoji)} {existing.get('name', ai_category)}", ai_confidence
        else:
            return original_category, 0.5
            
    except Exception as e:
        logger.warning(f"Failed to enhance category for user {user_id}: {str(e)}")
        return original_category, 0.5


async def process_extracted_transactions(message: Message, transactions: list, user_id: int, language: str, current_date: str, custom_cats: list = None, ai_reply: str = None, habits: dict = None, state: FSMContext = None, tip: str = None):
    # ── Defensive lokal binding (UnboundLocalError oldini olish) ──
    from src.services.groq_service import groq_service as _gs
    groq_service = _gs

    if not transactions:
        await message.answer(t(language, "voice_not_understood"))
        return

    for tx in transactions:
        tx_type = tx.get("transaction_type", tx.get("type"))
        amount = tx.get("amount", 0)
        
        # JSON format va turi validatsiyasi
        if tx_type not in ["kirim", "chiqim", "qarz"]:
            await message.answer("🤔 Ma'lumotni to'liq tushunmadim. Aniqroq yozib ko'ring: '15,000 so'm taksiga ketdi'")
            continue
            
        try:
            amount = float(amount)
        except:
            await message.answer("🤔 Summani tushunmadim. Masalan: '15000' yoki '15k' yozing.")
            continue
            
        if amount < 0:
            await message.answer("❌ Summa manfiy bo'lishi mumkin emas. To'g'ri summani yozing.")
            continue
        if amount == 0:
            await message.answer("❌ Summa 0 bo'lishi mumkin emas.")
            continue
            
        currency = tx.get("currency", "UZS").upper()
        if currency not in ["UZS", "USD", "RUB", "KZT"]:
            await message.answer("🤔 Valyutani tushunmadim. Faqat UZS, USD, RUB, KZT qabul qilinadi.")
            continue
            
        # 1 trilliondan katta summa
        if amount > 1000000000000:
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Ha, to'g'ri", callback_data="confirm_large_yes"),
                    InlineKeyboardButton(text="✏️ O'zgartirish", callback_data="confirm_large_no")
                ]
            ])
            await message.answer(f"⚠️ {format_number(amount)} {currency} — Bu juda katta summa. To'g'ri kiritdingizmi?", reply_markup=kb)
            if state:
                await state.set_state(TransactionAmbiguity.confirm_large_amount)
                await state.update_data(pending_tx=tx)
            return

        date_str = tx.get("date", current_date)
        display_date = parse_display_date(date_str)
        category = tx.get("category", "📋 Boshqa")
        description = tx.get("description", "")
        ai_bal_name = tx.get("balance_name")
        
        from src.database import resolve_balance_name, update_shared_wallet_balance, get_user_all_balances
        bal_type, bal_id = await resolve_balance_name(user_id, ai_bal_name)
        
        all_balances = await get_user_all_balances(user_id)
        
        # Agar shared bo'lsa, currency ni wallet currency ga o'zgartiramiz
        if bal_type == 'shared':
            from src.database import shared_wallets_collection
            from bson import ObjectId
            sw = await shared_wallets_collection.find_one({"_id": ObjectId(bal_id)})
            if sw:
                currency = sw.get("currency", currency)
                account_name = sw.get("name", "Umumiy Hisob")
            else:
                account_name = currency
        else:
            account_name = all_balances.get(currency, {}).get("title", currency)

        try:
            await ensure_balance_exists(user_id, currency)
        except Exception as e:
            log_error(ErrorType.MONGODB_GENERAL, f"ensure_balance_exists failed", user_id, e)
            await message.answer(t(language, "err_db_connection"))
            continue

        # ════════════════════════════
        #  KIRIM
        # ════════════════════════════
        if tx_type == "kirim":
            # Enhance category with AI detection
            enhanced_category, confidence = await enhance_category_with_ai(
                description=description,
                original_category=category,
                personal_cats=custom_cats,
                user_id=user_id,
                tx_type="kirim"
            )
            
            try:
                tx_payload = {
                    "telegram_id": user_id,
                    "type": "kirim",
                    "amount": amount,
                    "currency": currency,
                    "date": date_str,
                    "description": description,
                    "category": enhanced_category,
                    "category_confidence": confidence,
                    "affects_balance": True,
                }
                if bal_type == 'shared':
                    tx_payload["wallet_id"] = bal_id
                    new_balance = await update_shared_wallet_balance(bal_id, amount, is_income=True)
                    asyncio.create_task(notify_shared_wallet_members(bal_id, user_id, "kirim", amount, currency, enhanced_category))
                else:
                    new_balance = await update_user_balance(user_id, currency, amount, is_income=True)
                
                tx_id = await insert_transaction(tx_payload)

            except Exception as e:
                log_error(ErrorType.MONGODB_GENERAL, f"Failed to save income transaction", user_id, e)
                await message.answer(t(language, "err_db_connection"))
                continue

            reply_head = ai_reply if ai_reply else "Hisobotga qo'shildi ✅"
            msg = (
                f"{reply_head}\n\n"
                f"💰 {t(language, 'tx_income')}:\n"
                f"📅 {t(language, 'tx_date', date=display_date)}\n"
                f"💵 {t(language, 'tx_amount', amount=format_number(amount), currency=currency)}\n"
                f"🏷 {t(language, 'tx_category', category=enhanced_category)}\n"
                f"📝 {t(language, 'tx_desc', description=description)}\n"
                f"💳 {t(language, 'tx_balance', account=account_name)}"
            )
            
            if tip:
                msg += f"\n\n💡 {tip}"
                
            tx_kb = build_tx_inline_keyboard(tx_id, language)
            await message.answer(msg, reply_markup=tx_kb)
            await save_chat_message(user_id, "assistant", msg, tx_id=str(tx_id))

        # ════════════════════════════
        #  CHIQIM
        # ════════════════════════════
        elif tx_type == "chiqim":
            # Enhance category with AI detection
            enhanced_category, confidence = await enhance_category_with_ai(
                description=description,
                original_category=category,
                personal_cats=custom_cats,
                user_id=user_id,
                tx_type="chiqim"
            )
            
            # Anomaly Detection (QISM 5)
            if habits and "category_averages" in habits:
                clean_cat = category.replace("📦 ", "").strip()
                avg_amount = habits["category_averages"].get(clean_cat)
                
                # Agar o'rtacha qiymat bo'lsa va joriy summa undan 10 marta katta bo'lsa
                if avg_amount and amount > (avg_amount * 10):
                    if state:
                        # Saqlab turamiz va tasdiqlash so'raymiz
                        pending_tx = {
                            "type": "chiqim",
                            "amount": amount,
                            "currency": currency,
                            "date": date_str,
                            "description": description,
                            "category": enhanced_category,
                            "category_confidence": confidence
                        }
                        await state.update_data(pending_tx=pending_tx, ai_reply=ai_reply)
                        
                        kb = InlineKeyboardMarkup(inline_keyboard=[
                            [
                                InlineKeyboardButton(text="✅ Ha", callback_data="anomaly:confirm"),
                                InlineKeyboardButton(text="✏️ Tahrirlash", callback_data="anomaly:edit")
                            ]
                        ])
                        await message.answer(f"Tasdiqlaysizmi? Bu summa odatdagidan ancha katta:\n💸 {format_number(amount)} {currency} — {enhanced_category}", reply_markup=kb)
                        return # Iteratsiyani to'xtatamiz
            
            limit_warning = ""
            advice_msg = ""
            try:
                tx_payload = {
                    "telegram_id": user_id,
                    "type": "chiqim",
                    "amount": amount,
                    "currency": currency,
                    "date": date_str,
                    "description": description,
                    "category": enhanced_category,
                    "category_confidence": confidence,
                    "affects_balance": True,
                }
                if bal_type == 'shared':
                    tx_payload["wallet_id"] = bal_id
                    new_balance = await update_shared_wallet_balance(bal_id, amount, is_income=False)
                    # Notify members
                    asyncio.create_task(notify_shared_wallet_members(bal_id, user_id, "chiqim", amount, currency, enhanced_category))
                else:
                    new_balance = await update_user_balance(user_id, currency, amount, is_income=False)
                
                tx_id = await insert_transaction(tx_payload)

                
                if bal_type != 'shared':
                    monthly_total = await get_monthly_expense(user_id, currency)
                    limit_warning = await check_limit_warning(user_id, currency, monthly_total, language)
                    
                    # ─── AVTOMATIK MASLAHAT TEKSHIRUVI (LIMIT VA 40% KATEGORIYA) ───
                    from src.database import can_send_advice_today, get_financial_advice_context, get_user, update_last_advice_date


                    if await can_send_advice_today(user_id):
                        trigger = None
                        if limit_warning:
                            trigger = "limit_reached"
                        elif monthly_total > 0:
                            # Ushbu kategoriya jami xarajatning 40% dan oshdimi tekshiramiz
                            from datetime import datetime
                            from src.database import transactions_collection
                            today = datetime.utcnow()
                            first_day = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                            
                            cat_pipeline = [
                                {"$match": {
                                    "telegram_id": user_id,
                                    "currency": currency,
                                    "type": "chiqim",
                                    "category": enhanced_category,
                                    "affects_balance": True,
                                    "created_at": {"$gte": first_day}
                                }},
                                {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
                            ]
                            cat_res = await transactions_collection.aggregate(cat_pipeline).to_list(length=1)
                            if cat_res:
                                cat_total = cat_res[0].get("total", 0)
                                if (cat_total / monthly_total) >= 0.4:
                                    trigger = "category_high"
                        
                        if trigger:
                            user_data = await get_user(user_id)
                            context_data = await get_financial_advice_context(user_id, currency)
                            advice_msg = await groq_service.generate_smart_financial_advice(
                                user_context=user_data,
                                financial_data=context_data,
                                trigger_type=trigger,
                                language=language
                            )
                            await update_last_advice_date(user_id)

            except Exception as e:
                log_error(ErrorType.MONGODB_GENERAL, f"Failed to save expense transaction", user_id, e)
                await message.answer(t(language, "err_db_connection"))
                continue

            reply_head = ai_reply if ai_reply else "Hisobotga qo'shildi ✅"
            msg = (
                f"{reply_head}\n\n"
                f"💸 {t(language, 'tx_expense')}:\n"
                f"📅 {t(language, 'tx_date', date=display_date)}\n"
                f"💵 {t(language, 'tx_amount', amount=format_number(amount), currency=currency)}\n"
                f"🏷 {t(language, 'tx_category', category=enhanced_category)}\n"
                f"📝 {t(language, 'tx_desc', description=description)}\n"
                f"💳 {t(language, 'tx_balance', account=account_name)}"
            )
            
            if limit_warning:
                msg += f"\n\n⚠️ {limit_warning}"
            
            if advice_msg:
                msg += f"\n\n{advice_msg}"
            
            if tip:
                msg += f"\n\n💡 {tip}"
                
            tx_kb = build_tx_inline_keyboard(tx_id, language)
            await message.answer(msg, reply_markup=tx_kb)
            await save_chat_message(user_id, "assistant", msg, tx_id=str(tx_id))



        # ════════════════════════════
        #  QARZ
        # ════════════════════════════
        elif tx_type == "qarz":
            debt_info = tx.get("debt_info", {})
            person = tx.get("person") or debt_info.get("person", "")
            
            if not person or person.lower() == "noma'lum":
                await message.answer("Kimga/kimdan qarz? Ism yoki laqab yozing.")
                if state:
                    await state.set_state(TransactionAmbiguity.waiting_for_person_name)
                    await state.update_data(pending_tx=tx)
                return

            direction = tx.get("direction") or debt_info.get("direction", "bergan")
            due_date = tx.get("due_date") or debt_info.get("due_date", "nomalum")
            
            if due_date != "nomalum":
                try:
                    dd = datetime.strptime(due_date, "%Y-%m-%d")
                    now_d = datetime.now()
                    if dd.date() < now_d.date():
                        kb = InlineKeyboardMarkup(inline_keyboard=[
                            [
                                InlineKeyboardButton(text="✅ Ha", callback_data="confirm_past_date_yes"),
                                InlineKeyboardButton(text="📅 Yangi sana", callback_data="confirm_past_date_no")
                            ]
                        ])
                        await message.answer(f"⚠️ Bu sana ({parse_display_date(due_date)}) o'tib ketgan. Qarzni baribir saqlaymizmi?", reply_markup=kb)
                        if state:
                            await state.set_state(TransactionAmbiguity.confirm_past_due_date)
                            await state.update_data(pending_tx=tx)
                        return
                except:
                    pass

            reminder_date = tx.get("reminder_date")
            reminder_time = tx.get("reminder_time")

            try:
                debt_id = await insert_debt({
                    "telegram_id": user_id,
                    "direction": direction,
                    "amount": amount,
                    "currency": currency,
                    "person": person,
                    "due_date": due_date,
                    "status": "active",
                    "paid_amount": 0,
                    "description": description,
                    "reminder_date": reminder_date,
                    "reminder_time": reminder_time
                })

                if reminder_date and reminder_time:
                    try:
                        rem_dt = datetime.strptime(f"{reminder_date} {reminder_time}", "%Y-%m-%d %H:%M")
                        await process_reminders(user_id, [{
                            "type": "financial",
                            "message": f"{person} bilan qarz oldi-berdisi! ({format_number(amount)} {currency})",
                            "time": rem_dt.strftime("%Y-%m-%d %H:%M")
                        }], related_debt_id=debt_id)
                    except Exception as e:
                        logger.error(f"Failed to schedule debt reminder: {e}")

                b_uzs = await get_user_balance(user_id, "UZS")
                b_usd = await get_user_balance(user_id, "USD")
            except Exception as e:
                log_error(ErrorType.MONGODB_GENERAL, f"Failed to save debt", user_id, e)
                await message.answer(t(language, "err_db_connection"))
                continue

            direction_text = "Sen berding (olishim kerak)" if direction == "bergan" else "Sen olding (qaytarishim kerak)"
            reply_head = ai_reply if ai_reply else t(language, 'tx_saved')
            
            msg = (
                f"{reply_head}\n\n"
                f"🤝 Qarz:\n"
                f"📅 Sana: {parse_display_date(date_str)}\n"
                f"👤 Shaxs: {person}\n"
                f"💵 Miqdor: {format_number(amount)} {currency}\n"
                f"📌 Tur: {direction_text}\n"
                f"⏰ Muddat: {parse_display_date(due_date)}\n"
            )
            if reminder_date:
                msg += f"⏰ Eslatma: {parse_display_date(reminder_date)} {reminder_time}\n"
            if description:
                msg += f"📝 Izoh: {description}\n"
            msg += f"━━━━━━━━━━━━━━━━\n💰 Balans: {format_number(b_uzs)} UZS | {format_number(b_usd)} USD\n(Qarz balansga ta'sir qilmadi)"

            debt_kb = await build_debt_webapp_keyboard(debt_id, language)
            await message.answer(msg, reply_markup=debt_kb)
            await save_chat_message(user_id, "assistant", msg, debt_id=str(debt_id))


# ─── AMBIGUITY PROTOCOL FSM HANDLERS ───

@router.message(TransactionAmbiguity.waiting_for_amount, F.text)
async def resolve_missing_amount(message: Message, state: FSMContext):
    text = message.text
    # Simple extraction for amount (AI is skipped to save tokens)
    import re
    digits = re.sub(r'[^\d]', '', text)
    if not digits:
        await message.answer("Miqdor faqat raqamlardan iborat bo'lishi kerak. Qayta kiriting:")
        return
        
    amount = float(digits)
    # Check for multiplier
    if "ming" in text.lower(): amount *= 1000
    if "mln" in text.lower() or "million" in text.lower(): amount *= 1000000
    
    data = await state.get_data()
    tx = data.get("partial_tx", {})
    tx["amount"] = amount
    
    # Check if currency was mentioned
    if "dollar" in text.lower() or "$" in text: tx["currency"] = "USD"
    if "rubl" in text.lower(): tx["currency"] = "RUB"
    
    await state.clear()
    user = await get_user(message.from_user.id)
    await process_extracted_transactions(message, [tx], message.from_user.id, user.get("language", "uz"), datetime.now().strftime("%Y-%m-%d"))


@router.callback_query(F.data.startswith("resolve_type:"), TransactionAmbiguity.waiting_for_type)
async def resolve_missing_type(callback: CallbackQuery, state: FSMContext):
    tx_type = callback.data.split(":")[1]
    
    data = await state.get_data()
    tx = data.get("partial_tx", {})
    tx["type"] = tx_type
    
    await state.clear()
    await callback.message.edit_text("✅ Tur qabul qilindi.")
    user = await get_user(callback.from_user.id)
    await process_extracted_transactions(callback.message, [tx], callback.from_user.id, user.get("language", "uz"), datetime.now().strftime("%Y-%m-%d"))


@router.callback_query(F.data.startswith("resolve_date:"), TransactionAmbiguity.waiting_for_debt_date)
async def resolve_missing_debt_date(callback: CallbackQuery, state: FSMContext):
    action = callback.data.split(":")[1]
    data = await state.get_data()
    tx = data.get("partial_tx", {})
    
    if action == "skip":
        tx["due_date"] = "nomalum"
        await state.clear()
        await callback.message.edit_text("✅ Muddat belgilanmadi.")
        user = await get_user(callback.from_user.id)
        await process_extracted_transactions(callback.message, [tx], callback.from_user.id, user.get("language", "uz"), datetime.now().strftime("%Y-%m-%d"))
    else:
        await callback.message.edit_text("Qachon qaytaradi? Sanani yozing (masalan, 'ertaga' yoki '25-may')")
        # We can re-use the current state but wait for text
        pass

@router.message(TransactionAmbiguity.waiting_for_debt_date, F.text)
async def resolve_missing_debt_date_text(message: Message, state: FSMContext):
    # Here we would ideally ask Groq to parse the date, but to save tokens we just set it as string
    data = await state.get_data()
    tx = data.get("partial_tx", {})
    tx["due_date"] = message.text
    
    await state.clear()
    user = await get_user(message.from_user.id)
    await process_extracted_transactions(message, [tx], message.from_user.id, user.get("language", "uz"), datetime.now().strftime("%Y-%m-%d"))


# ═══════════════════════════════════════
# ANOMALY DETECTION HANDLERS (QISM 5)
# ═══════════════════════════════════════

@router.callback_query(F.data == "anomaly:confirm")
async def anomaly_confirm_handler(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    pending_tx = data.get("pending_tx")
    ai_reply = data.get("ai_reply")
    
    if not pending_tx:
        await callback.answer("Xatolik: Tranzaksiya topilmadi", show_alert=True)
        return
        
    await state.clear()
    await callback.message.delete() # Remove the "Tasdiqlaysizmi?" message
    user = await get_user(callback.from_user.id)
    language = user.get("language", "uz")
    
    await process_extracted_transactions(
        callback.message, 
        [pending_tx], 
        callback.from_user.id, 
        language, 
        datetime.now().strftime("%Y-%m-%d"), 
        None, 
        ai_reply
    )

@router.callback_query(F.data == "anomaly:edit")
async def anomaly_edit_handler(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("To'g'ri summani kiriting (faqat raqamlarda):")
    await state.set_state(TransactionAmbiguity.editing_anomaly_amount)

@router.message(TransactionAmbiguity.editing_anomaly_amount, F.text)
async def anomaly_edit_amount_text(message: Message, state: FSMContext):
    text = message.text.replace(" ", "").replace(",", "")
    if not text.isdigit():
        await message.answer("Iltimos, faqat raqam kiriting.")
        return
        
    new_amount = float(text)
    
    data = await state.get_data()
    pending_tx = data.get("pending_tx")
    ai_reply = data.get("ai_reply")
    
    if not pending_tx:
        await state.clear()
        return
        
    pending_tx["amount"] = new_amount
    await state.clear()
    
    user = await get_user(message.from_user.id)
    language = user.get("language", "uz")
    
    await process_extracted_transactions(
        message, 
        [pending_tx], 
        message.from_user.id, 
        language, 
        datetime.now().strftime("%Y-%m-%d"), 
        None, 
        ai_reply
    )


# ═══════════════════════════════════════
# INLINE CALLBACK HANDLERS (Debt actions)
# ═══════════════════════════════════════

@router.callback_query(F.data.startswith("debt_paid:"))
async def handle_debt_paid(callback: CallbackQuery):
    """Qarz qaytarildi deb belgilash."""
    from src.database import update_debt_status, get_debt_by_id, insert_transaction, update_user_balance
    debt_id = callback.data.split(":")[1]
    
    debt = await get_debt_by_id(debt_id)
    if not debt:
        await callback.answer("Qarz topilmadi", show_alert=True)
        return
    
    user = await get_user(callback.from_user.id)
    language = user.get("language", "uz")
    
    await update_debt_status(debt_id, 'paid')
    
    # Cancel related reminders
    from src.database import reminders_collection
    from datetime import datetime
    await reminders_collection.update_many(
        {"related_debt_id": debt_id, "status": "pending"},
        {"$set": {"status": "done", "updated_at": datetime.utcnow()}}
    )
    
    # Balansni yangilash
    t_type = "kirim" if debt.get("direction") == "bergan" else "chiqim"
    amount = debt.get("amount", 0) - debt.get("paid_amount", 0)
    currency = debt.get("currency", "UZS")
    
    tx_data = {
        "telegram_id": debt.get("telegram_id", callback.from_user.id),
        "type": t_type,
        "amount": amount,
        "currency": currency,
        "category": "🔄 Qarz qaytdi" if t_type == "kirim" else "🔄 Qarz uzildi",
        "description": f"{debt.get('person')} bilan qarz hisob-kitobi",
        "affects_balance": True
    }
    await insert_transaction(tx_data)
    await update_user_balance(tx_data["telegram_id"], currency, amount, is_income=(t_type == "kirim"))
    
    person = debt.get("person", "Noma'lum")
    await callback.message.edit_text(
        f"✅ {person} bilan qarz yakunlandi!\n"
        f"💰 {format_number(amount)} {currency} balansga qo'shildi."
    )
    await callback.answer("✅ Qarz qaytarildi!")


@router.callback_query(F.data.startswith("debt_delete:"))
async def handle_debt_delete(callback: CallbackQuery):
    """Qarz o'chirish."""
    from src.database import delete_debt, get_debt_by_id
    debt_id = callback.data.split(":")[1]
    
    debt = await get_debt_by_id(debt_id)
    if not debt:
        await callback.answer("Qarz topilmadi", show_alert=True)
        return
    
    await delete_debt(debt_id)
    
    person = debt.get("person", "Noma'lum")
    amount = debt.get("amount", 0) - debt.get("paid_amount", 0)
    currency = debt.get("currency", "UZS")
    
    await callback.message.edit_text(
        f"🗑 Qarz o'chirildi.\n"
        f"👤 {person} — {format_number(amount)} {currency}"
    )
    await callback.answer("❌ Qarz o'chirildi")


@router.callback_query(F.data.startswith("debt_not_paid:"))
async def handle_debt_not_paid(callback: CallbackQuery):
    """Qarz hali qaytarilmadi → muddatni 7 kunga uzaytirish."""
    from src.database import get_debt_by_id, update_debt_due_date
    debt_id = callback.data.split(":")[1]
    
    debt = await get_debt_by_id(debt_id)
    if not debt:
        await callback.answer("Qarz topilmadi", show_alert=True)
        return
    
    # Muddatni 7 kunga uzaytirish
    from datetime import timedelta as td
    try:
        old_due = datetime.strptime(debt.get("due_date", ""), "%Y-%m-%d")
    except (ValueError, TypeError):
        old_due = datetime.now()
    
    new_due = old_due + td(days=7)
    new_due_str = new_due.strftime("%Y-%m-%d")
    await update_debt_due_date(debt_id, new_due_str)
    
    person = debt.get("person", "Noma'lum")
    amount = debt.get("amount", 0) - debt.get("paid_amount", 0)
    currency = debt.get("currency", "UZS")
    
    await callback.message.edit_text(
        f"⏰ Muddat uzaytirildi!\n"
        f"👤 {person} — {format_number(amount)} {currency}\n"
        f"📅 Yangi muddat: {new_due.strftime('%d.%m.%Y')}",
        reply_markup=build_debt_keyboard(debt_id)
    )
    await callback.answer("⏰ Muddat 7 kunga uzaytirildi")


# ═══════════════════════════════════════
# QUICK TRANSACTION ACTION CALLBACKS
# ═══════════════════════════════════════

async def check_tx_expiry(callback: CallbackQuery, tx_id: str) -> bool:
    """Check if transaction interaction has expired (> 24h)."""
    from src.database import get_transaction_by_id
    from datetime import datetime, timedelta
    tx = await get_transaction_by_id(tx_id)
    if not tx:
        await callback.answer("Tranzaksiya topilmadi.", show_alert=True)
        return False
        
    created_at = tx.get("created_at")
    if not created_at:
        return True # Assume not expired if no date
        
    if datetime.utcnow() - created_at > timedelta(hours=24):
        lang = "uz" # Default
        kb = await build_webapp_keyboard("/", lang, button_text="📊 Mini Appni ochish")
        await callback.message.edit_text(
            "Bu amal endi mavjud emas. Mini Appdan tahrirlang 👇",
            reply_markup=kb
        )
        await callback.answer("Vaqt o'tdi.")
        return False
    return True


@router.callback_query(F.data.startswith("edit_cat:"))
async def handle_edit_cat_btn(callback: CallbackQuery):
    parts = callback.data.split(":")
    tx_id = parts[1]
    page = int(parts[2])
    
    if not await check_tx_expiry(callback, tx_id): return
    
    kb = build_category_selector_keyboard(tx_id, page)
    await callback.message.edit_reply_markup(reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("edit_bal:"))
async def handle_edit_bal_btn(callback: CallbackQuery):
    tx_id = callback.data.split(":")[1]
    if not await check_tx_expiry(callback, tx_id): return
    
    kb = await build_balance_selector_keyboard(tx_id, callback.from_user.id)
    await callback.message.edit_reply_markup(reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("del_tx:"))
async def handle_del_tx_btn(callback: CallbackQuery):
    tx_id = callback.data.split(":")[1]
    if not await check_tx_expiry(callback, tx_id): return
    
    from src.database import get_transaction_by_id
    tx = await get_transaction_by_id(tx_id)
    
    kb = build_delete_confirm_keyboard(tx_id)
    await callback.message.edit_text(
        f"Haqiqatan o'chirasizmi?\n{format_number(tx['amount'])} {tx['currency']} — {tx['category']}",
        reply_markup=kb
    )
    await callback.answer()


@router.callback_query(F.data.startswith("set_cat:"))
async def handle_set_cat(callback: CallbackQuery):
    parts = callback.data.split(":")
    tx_id = parts[1]
    new_cat_name = parts[2]
    
    if not await check_tx_expiry(callback, tx_id): return
    
    from src.database import change_transaction_category, get_transaction_by_id
    from src.categories import find_system_category
    
    # Full category name check (callback might be truncated)
    cat_obj = find_system_category(new_cat_name)
    full_cat_display = f"{cat_obj['emoji']} {cat_obj['name']}" if cat_obj else new_cat_name
    
    tx = await get_transaction_by_id(tx_id)
    old_cat = tx.get("category", "Noma'lum")
    
    await change_transaction_category(tx_id, full_cat_display)
    
    await callback.message.edit_text(f"✅ Kategoriya o'zgartirildi:\n{old_cat} → {full_cat_display}")
    await callback.answer("Muvaffaqiyatli!")


@router.callback_query(F.data.startswith("set_bal:"))
async def handle_set_bal(callback: CallbackQuery):
    parts = callback.data.split(":")
    tx_id = parts[1]
    new_curr = parts[2]
    
    if not await check_tx_expiry(callback, tx_id): return
    
    from src.database import change_transaction_balance, get_transaction_by_id, get_user_all_balances
    tx = await get_transaction_by_id(tx_id)
    old_curr = tx.get("currency", "UZS")
    
    user_id = callback.fromuser.id if hasattr(callback, 'fromuser') else callback.from_user.id
    all_balances = await get_user_all_balances(user_id)
    
    old_title = all_balances.get(old_curr, {}).get("title", old_curr)
    new_title = all_balances.get(new_curr, {}).get("title", new_curr)
    
    await change_transaction_balance(tx_id, new_curr)
    
    await callback.message.edit_text(f"✅ Hisob o'zgartirildi:\n{old_title} → {new_title}")
    await callback.answer("Muvaffaqiyatli!")


@router.callback_query(F.data.startswith("confirm_del:"))
async def handle_confirm_del(callback: CallbackQuery):
    tx_id = callback.data.split(":")[1]
    
    from src.database import confirm_delete_transaction_logic
    success = await confirm_delete_transaction_logic(tx_id)
    
    if success:
        await callback.message.edit_text("🗑 Tranzaksiya o'chirildi va balans qayta hisoblandi.")
        await callback.answer()
    else:
        await callback.answer("Xatolik yoki allaqachon o'chirilgan.", show_alert=True)


@router.callback_query(F.data.startswith("tx_back:"))
async def handle_tx_back(callback: CallbackQuery):
    tx_id = callback.data.split(":")[1]
    if not await check_tx_expiry(callback, tx_id): return
    
    from src.database import get_transaction_by_id, get_user_all_balances, resolve_balance_name
    tx = await get_transaction_by_id(tx_id)
    if not tx:
        await callback.answer("Tranzaksiya topilmadi.", show_alert=True)
        return
    user_id = callback.fromuser.id if hasattr(callback, 'fromuser') else callback.from_user.id
    
    ai_bal_name = tx.get("balance_name")
    currency = tx.get("currency", "UZS").upper()
    bal_type, bal_id = await resolve_balance_name(user_id, ai_bal_name)
    all_balances = await get_user_all_balances(user_id)
    
    if bal_type == 'shared':
        from src.database import shared_wallets_collection
        from bson import ObjectId
        sw = await shared_wallets_collection.find_one({"_id": ObjectId(bal_id)})
        if sw:
            currency = sw.get("currency", currency)
            account_name = sw.get("name", "Umumiy Hisob")
        else:
            account_name = currency
    else:
        account_name = all_balances.get(currency, {}).get("title", currency)
    
    display_date = parse_display_date(tx['date'])
    is_inc = (tx['type'] == 'kirim')
    
    msg = (
        "Hisobotga qo'shildi ✅\n\n"
        f"{'💰 Kirim:' if is_inc else '💸 Chiqim:'}\n"
        f"📅 Sana: {display_date}\n"
        f"💵 Summa: {format_number(tx['amount'])} {currency}\n"
        f"🏷 Kategoriya: {tx['category']}\n"
        f"📝 Izoh: {tx.get('description', '')}\n"
        f"💳 Balans: {account_name}"
    )
    
    tx_kb = build_tx_inline_keyboard(tx_id)
    await callback.message.edit_text(msg, reply_markup=tx_kb)
    await callback.answer()
    
    


# ═══════════════════════════════════════
# SMART REMINDER CALLBACKS
# ═══════════════════════════════════════

@router.callback_query(F.data.startswith("rem_done:"))
async def handle_reminder_done(callback: CallbackQuery):
    reminder_id = callback.data.split(":")[1]
    from src.database import update_reminder_status, reminders_collection, get_debt_by_id, update_debt_status, insert_transaction, update_user_balance
    from bson.objectid import ObjectId
    
    rem = await reminders_collection.find_one({"_id": ObjectId(reminder_id)})
    if rem and rem.get("related_debt_id"):
        debt_id = rem["related_debt_id"]
        debt = await get_debt_by_id(debt_id)
        if debt and debt.get("status") == "active":
            # Qarzni yopish
            await update_debt_status(debt_id, 'paid')
            t_type = "kirim" if debt.get("direction") == "bergan" else "chiqim"
            amount = debt.get("amount", 0) - debt.get("paid_amount", 0)
            currency = debt.get("currency", "UZS")
            
            tx_data = {
                "telegram_id": rem["user_id"],
                "type": t_type,
                "amount": amount,
                "currency": currency,
                "category": "🔄 Qarz (Eslatma)",
                "description": f"{debt.get('person')} bilan hisob-kitob",
                "affects_balance": True
            }
            await insert_transaction(tx_data)
            await update_user_balance(rem["user_id"], currency, amount, is_income=(t_type == "kirim"))
            await callback.message.answer(f"✅ Qarz yopildi va balans yangilandi.")

    await update_reminder_status(reminder_id, "done")
    await callback.message.edit_text("✅ Eslatma bajarildi deb belgilandi.")
    await callback.answer()


@router.callback_query(F.data.startswith("rem_later:"))
async def handle_reminder_later(callback: CallbackQuery):
    reminder_id = callback.data.split(":")[1]
    from src.database import update_reminder_time
    from datetime import datetime, timedelta
    
    new_time = datetime.now() + timedelta(hours=1)
    await update_reminder_time(reminder_id, new_time)
    
    await callback.message.edit_text("⏰ Eslatma 1 soatdan keyinga qoldirildi.")
    await callback.answer()


@router.callback_query(F.data.startswith("rem_cancel:"))
async def handle_reminder_cancel(callback: CallbackQuery):
    reminder_id = callback.data.split(":")[1]
    from src.database import update_reminder_status
    
    await update_reminder_status(reminder_id, "cancelled")
    await callback.message.edit_text("❌ Eslatma bekor qilindi.")
    await callback.answer()


async def notify_shared_wallet_members(wallet_id: str, actor_id: int, tx_type: str, amount: float, currency: str, category: str):
    from src.database import shared_wallets_collection, get_user
    from bson import ObjectId
    from src.bot import bot
    
    wallet = await shared_wallets_collection.find_one({"_id": ObjectId(wallet_id)})
    if not wallet: return
    
    actor = await get_user(actor_id)
    actor_name = actor.get("full_name", "A'zo")
    
    msg = (
        f"👥 {actor_name} '{wallet['name']}' hamyoniga kiritdi:\n"
        f"{'💸 Chiqim' if tx_type == 'chiqim' else '💰 Kirim'}: {format_number(amount)} {currency}\n"
        f"🏷 Kategoriya: {category}\n"
        f"💳 Yangi balans: {format_number(wallet['amount'])} {currency}"
    )
    
    for m in wallet.get("members", []):
        if m.get("user_id") != actor_id and m.get("status") == "active":
            try:
                await bot.send_message(chat_id=m["user_id"], text=msg)
            except Exception as e:
                logger.warning(f"Failed to notify shared wallet member {m.get('user_id')}: {e}")


@router.callback_query(F.data.startswith("sw_invite:"))
async def handle_sw_invite_callback(callback: CallbackQuery):
    _, action, invite_id = callback.data.split(":")
    
    from src.database import process_invite_action, shared_wallets_collection, get_user
    from bson import ObjectId
    from src.bot import bot
    
    invite = await process_invite_action(invite_id, action)
    if not invite:
        await callback.answer("Taklif topilmadi yoki allaqachon yakunlangan.")
        return
        
    wallet = await shared_wallets_collection.find_one({"_id": ObjectId(invite["wallet_id"])})
    
    if action == "accept":
        await callback.message.edit_text(f"✅ Siz '{wallet['name']}' umumiy hamyoniga qo'shildingiz!")
        # Notify owner
        target = await get_user(invite["to_user_id"])
        await bot.send_message(chat_id=invite["from_user_id"], text=f"👥 {target.get('full_name')} '{wallet['name']}' hamyoniga qo'shildi.")
    else:
        await callback.message.edit_text(f"❌ Siz '{wallet['name']}' hamyoniga qo'shilish taklifini rad etdingiz.")
        
    await callback.answer()

@router.callback_query(F.data == "confirm_large_yes", TransactionAmbiguity.confirm_large_amount)
async def confirm_large_amount_yes(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    tx = data.get("pending_tx", {})
    await state.clear()
    await callback.message.edit_text("✅ Katta summa tasdiqlandi.")
    user = await get_user(callback.from_user.id)
    # Re-route to process_parsed_data with this single transaction
    # We construct a fake data object
    fake_data = {"intent": "finance", "transactions": [tx]}
    from datetime import datetime
    await process_parsed_data(fake_data, callback.message, callback.from_user.id, user.get("language", "uz"), datetime.now().strftime("%Y-%m-%d"), None, state)

@router.callback_query(F.data == "confirm_large_no", TransactionAmbiguity.confirm_large_amount)
async def confirm_large_amount_no(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Bekor qilindi. To'g'ri summani boshqatdan kiriting.")
    await callback.answer()

@router.message(TransactionAmbiguity.waiting_for_person_name, F.text)
async def resolve_missing_person_name(message: Message, state: FSMContext):
    data = await state.get_data()
    tx = data.get("pending_tx", {})
    tx["person"] = message.text
    await state.clear()
    user = await get_user(message.from_user.id)
    fake_data = {"intent": "finance", "transactions": [tx]}
    from datetime import datetime
    await process_parsed_data(fake_data, message, message.from_user.id, user.get("language", "uz"), datetime.now().strftime("%Y-%m-%d"), None, state)

@router.callback_query(F.data == "confirm_past_date_yes", TransactionAmbiguity.confirm_past_due_date)
async def confirm_past_date_yes(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    tx = data.get("pending_tx", {})
    await state.clear()
    await callback.message.edit_text("✅ Qarz o'tgan sana bilan saqlanmoqda.")
    user = await get_user(callback.from_user.id)
    fake_data = {"intent": "finance", "transactions": [tx]}
    from datetime import datetime
    await process_parsed_data(fake_data, callback.message, callback.from_user.id, user.get("language", "uz"), datetime.now().strftime("%Y-%m-%d"), None, state)

@router.callback_query(F.data == "confirm_past_date_no", TransactionAmbiguity.confirm_past_due_date)
async def confirm_past_date_no(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Yangi sanani kiriting (masalan, 2026-05-01):")
    await state.set_state(TransactionAmbiguity.waiting_for_debt_date)
