"""
Scheduler — background tasks.
"""

import logging
from datetime import datetime, timedelta
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from src.database import (
    users_collection, debts_collection, transactions_collection,
    get_monthly_expense, get_monthly_income, get_user_balance,
    get_webapp_url
)
from src.config import ADMIN_ID

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()

# Bot reference uchun (dinamik eslatmalar uchun)
_bot_ref = None


def format_number(num: float) -> str:
    if num < 0:
        return "-" + f"{int(abs(num)):,}".replace(",", " ")
    return f"{int(num):,}".replace(",", " ")


# ═══════════════════════════════════════
# ERTALABGI ESLATMA (09:00)
# ═══════════════════════════════════════
async def check_morning_reminders(bot: Bot):
    cursor = users_collection.find({"settings.morning_reminder": True})
    users = await cursor.to_list(length=10000)

    for user in users:
        telegram_id = user["telegram_id"]
        first_name = user.get("full_name", "").split()[0] if user.get("full_name") else "do'stim"

        msg = (
            f"☀️ Assalomu alaykum, {first_name}!\n"
            f"Kuningiz hisobli o'tsin!\n"
            f"Xarajatlaringizni yuritishni unutmang 😇"
        )
        try:
            await bot.send_message(chat_id=telegram_id, text=msg)
        except Exception as e:
            logger.error(f"Morning reminder error for {telegram_id}: {e}")


# ═══════════════════════════════════════
# KUNDUZGI ESLATMA (15:00)
# ═══════════════════════════════════════
async def check_evening_reminders(bot: Bot):
    cursor = users_collection.find({"settings.evening_reminder": True})
    users = await cursor.to_list(length=10000)

    for user in users:
        telegram_id = user["telegram_id"]
        
        msg = (
            f"💬 Somly AI aloqada.\n"
            f"Ertalabdan hozirgacha bo'lgan\n"
            f"hisobingizni kiritdingizmi?\n"
            f"Esingizdan chiqmasidan yuborib \n"
            f"qo'ying. Bunga 30 soniya yetarli."
        )
        try:
            await bot.send_message(chat_id=telegram_id, text=msg)
        except Exception as e:
            logger.error(f"Evening reminder error for {telegram_id}: {e}")


# ═══════════════════════════════════════
# OYLIK XULOSA (Har oy 1-kuni)
# ═══════════════════════════════════════
async def check_monthly_summary(bot: Bot):
    # Bu funksiya 1-kun chaqiriladi, shuning uchun "o'tgan oy" ni olamiz
    today = datetime.utcnow()
    last_month = today.replace(day=1) - timedelta(days=1)
    start_of_last_month = last_month.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end_of_last_month = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0) - timedelta(seconds=1)

    months_uz = ["Yanvar", "Fevral", "Mart", "Aprel", "May", "Iyun", "Iyul", "Avgust", "Sentabr", "Oktabr", "Noyabr", "Dekabr"]
    month_name = months_uz[last_month.month - 1]

    cursor = users_collection.find({})
    users = await cursor.to_list(length=10000)

    for user in users:
        telegram_id = user["telegram_id"]
        currency = "UZS"

        pipeline = [
            {"$match": {
                "telegram_id": telegram_id,
                "currency": currency,
                "affects_balance": True,
                "created_at": {"$gte": start_of_last_month, "$lte": end_of_last_month}
            }},
            {"$group": {
                "_id": "$type",
                "total": {"$sum": "$amount"}
            }}
        ]
        
        res = await transactions_collection.aggregate(pipeline).to_list(length=2)
        totals = {r["_id"]: r["total"] for r in res}
        kirim = totals.get("kirim", 0)
        chiqim = totals.get("chiqim", 0)
        tejaldi = kirim - chiqim

        # Eng ko'p sarflagan kategoriya
        cat_pipeline = [
            {"$match": {
                "telegram_id": telegram_id,
                "type": "chiqim",
                "currency": currency,
                "created_at": {"$gte": start_of_last_month, "$lte": end_of_last_month}
            }},
            {"$group": {
                "_id": "$category",
                "total": {"$sum": "$amount"}
            }},
            {"$sort": {"total": -1}},
            {"$limit": 1}
        ]
        top_cat_res = await transactions_collection.aggregate(cat_pipeline).to_list(length=1)
        
        top_cat_str = ""
        if top_cat_res and chiqim > 0:
            cat_name = top_cat_res[0]["_id"]
            cat_total = top_cat_res[0]["total"]
            pct = int((cat_total / chiqim) * 100)
            top_cat_str = f"🏆 Eng ko'p sarflagan: {cat_name}\n   {format_number(cat_total)} {currency} ({pct}%)"

        msg = (
            f"📊 {month_name} oyining xulosasi:\n\n"
            f"💰 Jami kirim: {format_number(kirim)} {currency}\n"
            f"💸 Jami chiqim: {format_number(chiqim)} {currency}\n"
            f"✅ Tejaldi: {format_number(tejaldi)} {currency}\n\n"
            f"{top_cat_str}\n\n"
            f"Yangi oyda omad! 💪"
        )
        
        # ─── AQLLI MASLAHAT QO'SHISH ───
        try:
            from src.database import get_financial_advice_context, update_last_advice_date
            from src.services.groq_service import groq_service
            
            context_data = await get_financial_advice_context(telegram_id, currency)
            advice_msg = await groq_service.generate_smart_financial_advice(
                user_context=user,
                financial_data=context_data,
                trigger_type="monthly",
                language=user.get("language", "uz")
            )
            if advice_msg:
                msg += f"\n\n{advice_msg}"
                await update_last_advice_date(telegram_id)
        except Exception as e:
            logger.error(f"Monthly advice error for {telegram_id}: {e}")

        try:
            await bot.send_message(chat_id=telegram_id, text=msg)
        except Exception as e:
            pass


# ═══════════════════════════════════════
# QARZ ESLATMALARI (09:00)
# ═══════════════════════════════════════
async def check_debt_reminders(bot: Bot):
    today = datetime.utcnow().date()

    cursor = debts_collection.find({
        "status": {"$in": ["active", "partial"]},
    })
    debts = await cursor.to_list(length=1000)

    for debt in debts:
        due_date_str = debt.get("due_date")
        if not due_date_str or due_date_str == "nomalum":
            continue

        try:
            due_date = datetime.strptime(due_date_str, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            continue

        telegram_id = debt["telegram_id"]
        person = debt["person"]
        amount = debt["amount"] - debt.get("paid_amount", 0)
        currency = debt.get("currency", "UZS")
        direction = debt.get("direction", "bergan")
        debt_id = str(debt["_id"])

        if amount <= 0:
            continue

        delta = (due_date - today).days

        msg = None
        keyboard = None

        if direction == "bergan":
            # Ular senga qarzdir (Olishim kerak)
            if delta == 0:
                msg = (
                    f"🔔 Bugun!\n"
                    f"{person} {format_number(amount)} {currency} qaytarishi kerak edi.\n"
                    f"Qaytardimi?"
                )
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [
                        InlineKeyboardButton(text="✅ Qaytdi", callback_data=f"debt_paid:{debt_id}"),
                        InlineKeyboardButton(text="⏰ Uzayt", callback_data=f"debt_not_paid:{debt_id}")
                    ]
                ])
            elif delta < 0 and abs(delta) % 3 == 0:
                # Har 3 kunda bir
                msg = (
                    f"❗ Muddati o'tdi!\n"
                    f"{person} {format_number(amount)} {currency} qaytarmadi.\n"
                    f"{abs(delta)} kun kechikdi."
                )
        else:
            # Sen ularga qarzsan (Berishim kerak)
            if delta == 0:
                msg = (
                    f"🔔 Bugun!\n"
                    f"{person}ga {format_number(amount)} {currency} qaytarishingiz kerak edi.\n"
                    f"Qaytardingizmi?"
                )
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [
                        InlineKeyboardButton(text="✅ Qaytdi", callback_data=f"debt_paid:{debt_id}"),
                        InlineKeyboardButton(text="⏰ Uzayt", callback_data=f"debt_not_paid:{debt_id}")
                    ]
                ])
            elif delta < 0 and abs(delta) % 3 == 0:
                msg = (
                    f"❗ Muddati o'tdi!\n"
                    f"{person}ga {format_number(amount)} {currency} qaytarishingiz kerak edi.\n"
                    f"{abs(delta)} kun kechikdi."
                )

        if msg:
            try:
                if not keyboard:
                    # Oddiy eslatma uchun ham tugmalar
                    keyboard = InlineKeyboardMarkup(inline_keyboard=[
                        [
                            InlineKeyboardButton(text="✅ Qaytdi", callback_data=f"debt_paid:{debt_id}"),
                            InlineKeyboardButton(text="⏰ Uzayt", callback_data=f"debt_not_paid:{debt_id}")
                        ]
                    ])
                await bot.send_message(chat_id=telegram_id, text=msg, reply_markup=keyboard)
            except Exception as e:
                pass


# ═══════════════════════════════════════
# DATA INTEGRITY (02:00 AM)
# ═══════════════════════════════════════
async def daily_balance_integrity_check(bot: Bot):
    """
    Kunda bir marta (02:00) barcha balanslarni noldan hisoblab chiqadi.
    Agar joriy balans xato bo'lsa, to'g'irlaydi va adminga xabar beradi.
    """
    logger.info("Starting Daily Balance Integrity Check...")
    cursor = users_collection.find({})
    users = await cursor.to_list(length=10000)
    
    discrepancies = 0
    
    for user in users:
        telegram_id = user["telegram_id"]
        balances = user.get("balances", {})
        
        for currency, bal_data in balances.items():
            current_balance = float(bal_data.get("amount", 0))
            
            # Recalculate from pure transactions
            pipeline = [
                {"$match": {
                    "telegram_id": telegram_id,
                    "currency": currency,
                    "affects_balance": True
                }},
                {"$group": {
                    "_id": "$type",
                    "total": {"$sum": "$amount"}
                }}
            ]
            res = await transactions_collection.aggregate(pipeline).to_list(length=2)
            totals = {r["_id"]: float(r["total"]) for r in res}
            kirim = totals.get("kirim", 0.0)
            chiqim = totals.get("chiqim", 0.0)
            
            true_balance = kirim - chiqim
            
            if abs(current_balance - true_balance) > 0.01:
                # Discrepancy found! Fix it.
                await users_collection.update_one(
                    {"telegram_id": telegram_id},
                    {"$set": {f"balances.{currency}.amount": true_balance}}
                )
                discrepancies += 1
                logger.warning(f"Integrity check: User {telegram_id} {currency} balance corrected from {current_balance} to {true_balance}")
                
    if discrepancies > 0 and ADMIN_ID:
        try:
            await bot.send_message(chat_id=ADMIN_ID, text=f"⚠️ Tungi yaxlitlik tekshiruvi: {discrepancies} ta xato balans topildi va tuzatildi.")
        except Exception:
            pass
    logger.info(f"Daily Balance Integrity Check finished. Fixed {discrepancies} discrepancies.")


# ═══════════════════════════════════════
# WEEKLY CLEANUP (03:00 AM, Sunday)
# ═══════════════════════════════════════
async def weekly_cleanup(bot: Bot):
    """
    Inactive userlarni (6 oy) is_active=False qiladi va tozalash ishlarini bajaradi.
    """
    logger.info("Starting Weekly Cleanup...")
    six_months_ago = datetime.utcnow() - timedelta(days=180)
    
    res = await users_collection.update_many(
        {"last_active": {"$lt": six_months_ago}, "is_active": True},
        {"$set": {"is_active": False}}
    )
    
    if res.modified_count > 0:
        logger.info(f"Weekly cleanup: {res.modified_count} users marked as inactive.")


# ═══════════════════════════════════════
# SYSTEM MONITORING (Har 5 minut)
# ═══════════════════════════════════════
async def monitor_system_health(bot: Bot):
    """
    Har 5 minutda MongoDB va Groq API ni tekshiradi.
    Agar ishlamasa Adminga yozadi.
    """
    errors = []
    
    # 1. Check DB
    try:
        await users_collection.find_one({})
    except Exception as e:
        errors.append(f"❌ MongoDB ishlamayapti: {str(e)[:50]}")
        
    # 2. Check Groq API
    try:
        from src.services.groq_service import groq_service
        ks = groq_service.get_best_key()
        # Very lightweight check just to test connection
        await ks.client.models.list()
    except Exception as e:
        errors.append(f"❌ Groq API ishlamayapti: {str(e)[:50]}")
        
    if errors and ADMIN_ID:
        msg = "🚨 MONITORING ALERT:\n\n" + "\n".join(errors)
        try:
            await bot.send_message(chat_id=ADMIN_ID, text=msg)
        except Exception:
            pass


# ═══════════════════════════════════════
# GROQ API KEYS MONITORING
# ═══════════════════════════════════════
async def check_groq_keys_health(bot: Bot):
    """Har 5 minutda ishlaydi, Groq keylar holatini tekshiradi va log qiladi."""
    from src.services.groq_service import groq_service
    import time
    
    now = time.time()
    for ks in groq_service.keys_stats:
        if ks.status == "cooling" and now - ks.last_error_time > 60:
            ks.status = "active"
            ks.connection_errors = 0
            logger.info(f"Groq API Key {ks.index+1} reactivated via scheduler.")


async def send_daily_api_report(bot: Bot):
    """Har kuni 08:00 da admin ga Groq keylar hisobotini jo'natadi."""
    if not ADMIN_ID:
        return
        
    from src.services.groq_service import groq_service
    import time
    
    now = time.time()
    msg_parts = ["📊 API Keys holati:"]
    
    for ks in groq_service.keys_stats:
        if ks.status == "active":
            msg_parts.append(f"✅ Key {ks.index+1}: Aktiv ({ks.requests_count} so'rov)")
        elif ks.status == "cooling":
            rem = max(0, int(60 - (now - ks.last_error_time)))
            msg_parts.append(f"⚠️ Key {ks.index+1}: Cooling ({rem} soniya qoldi)")
        else:
            msg_parts.append(f"❌ Key {ks.index+1}: Exhausted")
            
    try:
        await bot.send_message(chat_id=ADMIN_ID, text="\n".join(msg_parts))
    except Exception as e:
        logger.error(f"Failed to send daily API report: {e}")

# ═══════════════════════════════════════
# AI TOMONIDAN YARATILGAN MAXSUS ESLATMALAR
# ═══════════════════════════════════════
async def check_custom_reminders(bot: Bot):
    """
    AI tomonidan 'reminders' kolleksiyasiga saqlangan vaqti kelgan eslatmalarni yuboradi.
    """
    from src.database import reminders_collection, update_reminder_status
    now = datetime.utcnow()
    try:
        cursor = reminders_collection.find({
            "status": "pending",
            "remind_at": {"$lte": now},
            "pending_transaction": {"$exists": False}
        })
        reminders = await cursor.to_list(length=50)
        
        for rem in reminders:
            user_id = rem.get("user_id")
            message = rem.get("message", "Eslatma!")
            reminder_id = str(rem["_id"])
            
            text = f"⏰ <b>Eslatma:</b>\n\n{message}"
            
            try:
                await bot.send_message(chat_id=user_id, text=text, parse_mode="HTML")
                await update_reminder_status(reminder_id, "sent")
                logger.info(f"Custom reminder {reminder_id} sent to {user_id}")
            except Exception as e:
                logger.error(f"Failed to send custom reminder to {user_id}: {e}")
                
    except Exception as e:
        logger.error(f"Error checking custom reminders: {e}")


# ═══════════════════════════════════════
# OYLIK DAROMAD DARAJASINI HISOBLASH
# ═══════════════════════════════════════
async def calculate_monthly_income_levels(bot: Bot):
    logger.info("Starting monthly income level calculation...")
    from src.database import transactions_collection, financial_history_collection
    
    now = datetime.utcnow()
    # Calculate for the previous month
    first_day_of_current_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    last_day_of_prev_month = first_day_of_current_month - timedelta(days=1)
    first_day_of_prev_month = last_day_of_prev_month.replace(day=1)
    
    month_str = last_day_of_prev_month.strftime("%Y-%m")
    
    # Check if we already calculated for this month
    existing = await financial_history_collection.count_documents({"month": month_str})
    if existing > 0:
        logger.info(f"Income history for {month_str} already exists. Skipping.")
        return
        
    pipeline = [
        {"$match": {
            "created_at": {"$gte": first_day_of_prev_month, "$lt": first_day_of_current_month},
            "affects_balance": True
        }},
        {"$group": {
            "_id": {"telegram_id": "$telegram_id", "type": "$type"},
            "total_amount": {"$sum": "$amount"},
            "count": {"$sum": 1}
        }},
        {"$group": {
            "_id": "$_id.telegram_id",
            "types": {"$push": {"type": "$_id.type", "amount": "$total_amount", "count": "$count"}}
        }}
    ]
    
    results = await transactions_collection.aggregate(pipeline).to_list(length=None)
    histories_to_insert = []
    
    for user_data in results:
        telegram_id = user_data["_id"]
        
        income_sum = 0
        expense_sum = 0
        income_count = 0
        
        for t in user_data["types"]:
            if t["type"] == "kirim":
                income_sum = float(t["amount"])
                income_count = t["count"]
            elif t["type"] == "chiqim":
                expense_sum = float(t["amount"])
                
        if income_count >= 2:
            level = "unknown"
            if income_sum < 2000000:
                level = "low"
            elif 2000000 <= income_sum <= 6000000:
                level = "medium"
            else:
                level = "high"
                
            histories_to_insert.append({
                "telegram_id": telegram_id,
                "month": month_str,
                "avg_income": income_sum,
                "avg_expense": expense_sum,
                "income_level": level,
                "calculated_at": datetime.utcnow()
            })
            
    if histories_to_insert:
        await financial_history_collection.insert_many(histories_to_insert)
        logger.info(f"Inserted {len(histories_to_insert)} income history records for {month_str}")
    else:
        logger.info(f"No valid income history found for {month_str}")


def setup_scheduler(bot: Bot):
    global _bot_ref
    _bot_ref = bot

    from src.services.currency_service import fetch_and_cache_cbu_rates
    
    # AI maxsus eslatmalari (birlashtirilgan job ichida chaqiriladi)
    # scheduler.add_job(check_custom_reminders, trigger="interval", minutes=1, args=[bot], id="custom_reminders", replace_existing=True)

    # Har 1 soatda valyuta kurslarini CBU dan olish
    scheduler.add_job(fetch_and_cache_cbu_rates, trigger="interval", hours=1, id="update_currency_rates", replace_existing=True)

    # Ertalab 09:00
    scheduler.add_job(check_morning_reminders, trigger="cron", hour=9, minute=0, args=[bot], id="morning_reminders", replace_existing=True)
    
    # Kunduzgi 15:00
    scheduler.add_job(check_evening_reminders, trigger="cron", hour=15, minute=0, args=[bot], id="evening_reminders", replace_existing=True)
    
    # Kunlik hisobot 23:00 da
    scheduler.add_job(check_daily_reports, trigger="cron", hour=23, minute=0, args=[bot], id="daily_reports", replace_existing=True)
    
    # Har oy 1-kuni 10:00 da
    scheduler.add_job(check_monthly_summary, trigger="cron", day=1, hour=10, minute=0, args=[bot], id="monthly_summary", replace_existing=True)
    
    # Qarzlar 09:00 da
    scheduler.add_job(check_debt_reminders, trigger="cron", hour=9, minute=0, args=[bot], id="debt_reminders", replace_existing=True)
    
    # Data Integrity haftada 1 marta Yakshanba 02:00 da
    scheduler.add_job(daily_balance_integrity_check, trigger="cron", day_of_week="sun", hour=2, minute=0, args=[bot], id="integrity_check", replace_existing=True)
    
    # Weekly Cleanup Yakshanba 03:00 da
    scheduler.add_job(weekly_cleanup, trigger="cron", day_of_week="sun", hour=3, minute=0, args=[bot], id="weekly_cleanup", replace_existing=True)
    
    # System Monitoring har 50 minutda
    scheduler.add_job(monitor_system_health, trigger="interval", minutes=50, args=[bot], id="system_monitoring", replace_existing=True)
    
    # Groq Keys Monitoring har 15 minutda
    scheduler.add_job(check_groq_keys_health, trigger="interval", minutes=15, args=[bot], id="groq_keys_health", replace_existing=True)
    
    # Groq Keys Kunlik Hisobot 08:00 da
    scheduler.add_job(send_daily_api_report, trigger="cron", hour=8, minute=0, args=[bot], id="daily_api_report", replace_existing=True)
    
    # Birlashtirilgan eslatmalarni tekshirish (AI va oddiy) har 2 daqiqada
    async def run_all_reminders(b):
        await check_custom_reminders(b)
        await check_pending_reminders(b)
        
    scheduler.add_job(run_all_reminders, trigger="interval", minutes=2, args=[bot], id="combined_reminders", replace_existing=True)
    
    # Segmentatsiya savollarini tekshirish (har 30 daqiqada)
    scheduler.add_job(check_segmentation_questions, trigger="interval", minutes=30, args=[bot], id="segmentation_questions", replace_existing=True)
    
    # Har oyning 1-kuni soat 01:00 da daromad tarixini hisoblash
    scheduler.add_job(calculate_monthly_income_levels, trigger="cron", day=1, hour=1, minute=0, args=[bot], id="monthly_income_levels", replace_existing=True)

    from src.services.scheduler import check_channel_subscriptions_job
    scheduler.add_job(check_channel_subscriptions_job, trigger="cron", hour=4, minute=0, args=[bot], id="check_channel_subs", replace_existing=True)

    scheduler.start()
    logger.info("Background scheduler started.")


# ═══════════════════════════════════════
# KANAL OBUNALARINI TEKSHIRISH (HAR KUNI)
# ═══════════════════════════════════════
async def check_channel_subscriptions_job(bot: Bot):
    """
    Har 24 soatda ishlaydi, obunasi tasdiqlangan userlarni kanaldan chiqqan-chiqmaganini tekshiradi.
    """
    from src.database import channel_subscriptions_collection, mark_channel_left
    
    # Faqat tasdiqlangan obunalarni tekshiramiz
    cursor = channel_subscriptions_collection.find({"confirmed": True})
    records = await cursor.to_list(length=100000)
    
    for r in records:
        user_id = r["user_id"]
        link = r["channel_link"]
        
        chat_identifier = link
        if "t.me/" in link and "+" not in link:
            username = link.split("t.me/")[1].split("/")[0]
            chat_identifier = f"@{username}"
            
        try:
            member = await bot.get_chat_member(chat_id=chat_identifier, user_id=user_id)
            if member.status in ["left", "kicked", "restricted"]:
                await mark_channel_left(user_id, link)
        except Exception as e:
            logger.warning(f"Background sub check failed for {chat_identifier} user {user_id}: {e}")


# ═══════════════════════════════════════
# XAVFSIZLIK: GROQ API KALITLARINI TEKSHIRISH
# ═══════════════════════════════════════
async def check_segmentation_questions(bot: Bot):
    """Har 5 daqiqada segmentation savollari kerak bo'lgan userlarni tekshiradi.
    Faqat 09:00–21:00 (UTC+5) oralig'ida yuboradi."""
    from src.database import get_pending_segmentation_users, users_collection
    from src.handlers.segment_handler import build_age_keyboard, build_country_keyboard
    from src.services.i18n import t
    import random

    try:
        users = await get_pending_segmentation_users()
        if not users:
            return

        for user in users:
            telegram_id = user["telegram_id"]
            lang = user.get("language", "uz")
            stage = user.get("segmentation_stage", 0)

            try:
                if stage == 0:
                    # 1-SAVOL: YOSH
                    kb = build_age_keyboard(lang)
                    await bot.send_message(
                        chat_id=telegram_id,
                        text=t(lang, "seg_age_question"),
                        reply_markup=kb
                    )
                    logger.info(f"Sent age question to user {telegram_id}")

                elif stage == 1:
                    # 2-SAVOL: JOYLASHUV
                    kb = build_country_keyboard(lang)
                    await bot.send_message(
                        chat_id=telegram_id,
                        text=t(lang, "seg_location_question"),
                        reply_markup=kb
                    )
                    logger.info(f"Sent location question to user {telegram_id}")

                # Agar javob bermasa, keyingi tekshiruvda yana 1-4 soatdan keyin qayta yuborish
                delay_hours = random.uniform(1, 4)
                next_time = datetime.utcnow() + timedelta(hours=delay_hours)
                await users_collection.update_one(
                    {"telegram_id": telegram_id},
                    {"$set": {"next_segment_time": next_time}}
                )

            except Exception as e:
                logger.error(f"Failed to send segmentation question to {telegram_id}: {e}")

    except Exception as e:
        logger.error(f"Error in check_segmentation_questions: {e}")


# ═══════════════════════════════════════
# SMART REMINDERS (Yangi)
# ═══════════════════════════════════════

async def check_pending_reminders(bot: Bot):
    """Pending holatdagi vaqti kelgan eslatmalarni yuboradi."""
    from src.database import get_pending_reminders, update_reminder_status
    from src.handlers.message_handler import build_reminder_keyboard
    
    reminders = await get_pending_reminders()
    if not reminders:
        return
        
    for r in reminders:
        user_id = r["user_id"]
        msg_text = r["message"]
        reminder_id = str(r["_id"])
        
        text = (
            f"⏰ Eslatma!\n\n"
            f"{msg_text}"
        )
        
        kb = build_reminder_keyboard(reminder_id)
        
        try:
            await bot.send_message(chat_id=user_id, text=text, reply_markup=kb)
            await update_reminder_status(reminder_id, "reminded")
        except Exception as e:
            logger.error(f"Failed to send reminder {reminder_id}: {e}")
    logger.info("Scheduler started — Cron jobs loaded.")
    logger.info("📅 Morning reminders at 09:00, Evening reminders at 15:00, Daily reports at 23:00, Currency updates every 1 hr.")


# ═══════════════════════════════════════
# KUNLIK HISOBOT (23:00)
# ═══════════════════════════════════════
async def check_daily_reports(bot: Bot):
    """
    Har kuni 23:00 da kunlik hisobot yuboradi.
    Balans, kirim, chiqim, qarz va eng ko'p sarflagan kategoriyani ko'rsatadi.
    """
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = datetime.utcnow().replace(hour=23, minute=59, second=59, microsecond=999999)
    today_date = datetime.utcnow().strftime("%d.%m.%Y")

    cursor = users_collection.find({})
    users = await cursor.to_list(length=10000)

    for user in users:
        telegram_id = user["telegram_id"]
        balances = user.get("balances", {})
        
        # Agar balans bo'lmasa, hisobot yubormasak bo'ladi
        if not balances:
            continue

        try:
            # ─── BALANSLAR ───
            balance_section = []
            emojis = {"UZS": "🟢", "USD": "🟡"}
            
            for currency, bal_data in balances.items():
                emoji = emojis.get(currency, "💵")
                amount = bal_data.get("amount", 0)
                balance_section.append(f"  {emoji} {currency}: {format_number(amount)} {currency}")

            # ─── TRANZAKSIYALAR (BUGUN) ───
            tx_cursor = transactions_collection.find({
                "telegram_id": telegram_id,
                "affects_balance": True,
                "created_at": {"$gte": today_start, "$lte": today_end}
            })
            today_txs = await tx_cursor.to_list(length=500)

            # Group by type and currency
            kirim_by_currency = {}
            chiqim_by_currency = {}
            
            for tx in today_txs:
                curr = tx.get("currency", "UZS")
                amount = tx["amount"]
                
                if tx["type"] == "kirim":
                    kirim_by_currency[curr] = kirim_by_currency.get(curr, 0) + amount
                else:
                    chiqim_by_currency[curr] = chiqim_by_currency.get(curr, 0) + amount

            # ─── KIRIM SECTION ───
            kirim_section = []
            total_kirim = sum(kirim_by_currency.values())
            
            if total_kirim > 0:
                for currency, amount in kirim_by_currency.items():
                    pct = int((amount / total_kirim) * 100) if total_kirim > 0 else 0
                    kirim_section.append(f"  {currency}: +{format_number(amount)} {currency} ({pct}%)")

            # ─── CHIQIM SECTION ───
            chiqim_section = []
            total_chiqim = sum(chiqim_by_currency.values())
            
            if total_chiqim > 0:
                for currency, amount in chiqim_by_currency.items():
                    chiqim_section.append(f"  {currency}: -{format_number(amount)} {currency}")

            # ─── QARZLAR ───
            debt_cursor = debts_collection.find({
                "telegram_id": telegram_id,
                "status": {"$in": ["active", "partial"]}
            })
            debts = await debt_cursor.to_list(length=500)
            
            berildi = 0  # Sen bergan (olishim kerak)
            olindi = 0   # Ular bergan (berishim kerak)
            
            for debt in debts:
                direction = debt.get("direction", "bergan")
                remaining = debt.get("amount", 0) - debt.get("paid_amount", 0)
                
                if direction == "bergan":  # Ular senga qarzdir (Olishim kerak)
                    berildi += remaining
                else:  # Sen ularga qarzsan (Berishim kerak)
                    olindi += remaining

            # ─── ENG KO'P SARFLAGAN KATEGORIYA ───
            cat_pipeline = [
                {"$match": {
                    "telegram_id": telegram_id,
                    "type": "chiqim",
                    "created_at": {"$gte": today_start, "$lte": today_end}
                }},
                {"$group": {
                    "_id": "$category",
                    "total": {"$sum": "$amount"}
                }},
                {"$sort": {"total": -1}},
                {"$limit": 1}
            ]
            top_cat_res = await transactions_collection.aggregate(cat_pipeline).to_list(length=1)
            top_category = ""
            if top_cat_res:
                cat_name = top_cat_res[0]["_id"]
                top_category = f"🏆 Eng ko'p: {cat_name}"

            # ─── XABAR QURISH ───
            msg_parts = [f"📊 {today_date} — Kunlik hisobingiz\n"]

            # Balanslar
            if balance_section:
                msg_parts.append("💳 Balanslar:")
                msg_parts.extend(balance_section)
                msg_parts.append("")

            # Kirim
            if kirim_section:
                msg_parts.append("💰 Kirim:")
                msg_parts.extend(kirim_section)
                msg_parts.append("")

            # Chiqim
            if chiqim_section:
                msg_parts.append("💸 Chiqim:")
                msg_parts.extend(chiqim_section)
                msg_parts.append("")

            # Qarzlar
            if berildi > 0 or olindi > 0:
                msg_parts.append("🤝 Qarzlar:")
                if berildi > 0:
                    msg_parts.append(f"  Berildi: {format_number(berildi)} UZS")
                if olindi > 0:
                    msg_parts.append(f"  Olindi: {format_number(olindi)} UZS")
                msg_parts.append("")

            # Eng ko'p
            if top_category:
                msg_parts.append(top_category)

            # Agar hisobda hech narsa bo'lmasa
            if len(msg_parts) == 1:  # Only the header
                msg_parts.append("Bugun hech narsa kiritilmadi.")

            msg = "\n".join(msg_parts)

            try:
                await bot.send_message(chat_id=telegram_id, text=msg)
                logger.info(f"Daily report sent to {telegram_id}")
            except Exception as e:
                logger.error(f"Failed to send daily report to {telegram_id}: {e}")

        except Exception as e:
            logger.error(f"Error generating daily report for {telegram_id}: {e}")


# ═══════════════════════════════════════
# DINAMIK ESLATMA (bir martalik)
# ═══════════════════════════════════════
async def send_one_time_reminder(telegram_id: int, text: str):
    """Bir martalik eslatma yuborish."""
    global _bot_ref
    if not _bot_ref:
        return
    try:
        await _bot_ref.send_message(chat_id=telegram_id, text=text)
        logger.info(f"One-time reminder sent to {telegram_id}")
    except Exception as e:
        logger.error(f"Failed to send one-time reminder to {telegram_id}: {e}")


def schedule_one_time_reminder(telegram_id: int, run_date: datetime, text: str):
    """Berilgan sanada bir marta ishlaydigan eslatma o'rnatadi."""
    job_id = f"reminder_{telegram_id}_{run_date.strftime('%Y%m%d%H%M')}"
    scheduler.add_job(
        send_one_time_reminder,
        trigger="date",
        run_date=run_date,
        args=[telegram_id, text],
        id=job_id,
        replace_existing=True,
    )
    logger.info(f"Scheduled one-time reminder for {telegram_id} at {run_date}")
