"""
Group handler — Telegram guruh eventlarini boshqarish.

Bot guruhga qo'shilganda:
- Guruh sozlangan bo'lsa → chat_id bog'lash, xush kelibsiz xabar
- Sozlanmagan bo'lsa → xabar + guruhni tark etish

Guruhda xabar kelganda:
- A'zo ro'yxatida bo'lsa → guruh balansiga yozish
"""

import logging
from aiogram import Router, F
from aiogram.types import ChatMemberUpdated, Message
from aiogram.filters import ChatMemberUpdatedFilter, IS_NOT_MEMBER, IS_MEMBER, ADMINISTRATOR
from src.database import (
    get_group_by_chat_id, get_user_groups, link_telegram_chat,
    insert_group_transaction, update_group_balance, get_user
)
from src.services.gemini_service import gemini_service, GeminiServerError
from src.database import get_custom_categories, get_user_financial_context, get_recent_transactions_context, get_user_habits

logger = logging.getLogger(__name__)
router = Router()


@router.my_chat_member(
    ChatMemberUpdatedFilter(member_status_changed=IS_NOT_MEMBER >> (IS_MEMBER | ADMINISTRATOR))
)
async def bot_added_to_group(event: ChatMemberUpdated):
    """Bot guruhga yoki kanalga qo'shilganda chaqiriladi."""
    chat_id = event.chat.id
    chat_title = event.chat.title or "Guruh"
    chat_type = event.chat.type  # "group", "supergroup", "channel"
    added_by = event.from_user.id

    logger.info(f"Bot added to {chat_type}: {chat_title} (id={chat_id}) by user {added_by}")

    # ════════════════════════════════════════════
    # KANAL — Bot kanalga qo'shilsa, hech narsa qilmaymiz (jim turadi)
    # Admin obuna tekshiruvi uchun bot kanalda bo'lishi SHART
    # ════════════════════════════════════════════
    if chat_type == "channel":
        logger.info(f"Bot added to CHANNEL: {chat_title} — staying silently for subscription checks")
        return

    # ════════════════════════════════════════════
    # GURUH — Mini App orqali sozlangan guruhmi tekshirish
    # ════════════════════════════════════════════
    # Tekshirish: bu foydalanuvchining sozlangan guruhi bormi?
    user_groups = await get_user_groups(added_by)
    unconfigured = True

    for group in user_groups:
        if not group.get("telegram_chat_id"):
            # Birinchi sozlangan lekin bog'lanmagan guruhni topamiz
            await link_telegram_chat(group["id"], chat_id)
            unconfigured = False

            await event.answer(
                f"✅ Somly AI guruhga muvaffaqiyatli ulandi!\n\n"
                f"📋 Guruh: {group['name']}\n"
                f"👥 A'zolar: {len(group.get('members', []))} ta\n\n"
                f"Endi guruh a'zolari botga xabar yuborganida "
                f"ma'lumotlar guruh balansiga qo'shiladi.\n\n"
                f"⚠️ Muhim: Meni guruhda admin qilib qo'ying, "
                f"aks holda xabarlarni o'qiy olmayman!"
            )
            break

    if unconfigured:
        # Guruh sozlanmagan — lekin chiqib ketmaymiz, faqat xabar
        await event.answer(
            "ℹ️ Somly AI guruhga qo'shildi!\n\n"
            "Guruh hisobi uchun Mini App dashboarddan "
            "guruhni sozlashingiz mumkin.\n\n"
            "📱 Mini App → Telegram guruh → Yangi guruh yaratish"
        )


@router.my_chat_member(
    ChatMemberUpdatedFilter(member_status_changed=(IS_MEMBER | ADMINISTRATOR) >> IS_NOT_MEMBER)
)
async def bot_removed_from_group(event: ChatMemberUpdated):
    """Bot guruhdan chiqarilganda."""
    chat_id = event.chat.id
    logger.info(f"Bot removed from group {chat_id}")
    # Guruh linkini tozalash kerak emas — foydalanuvchi qayta qo'shishi mumkin


@router.message(F.chat.type.in_({"group", "supergroup"}), F.text)
async def handle_group_message(message: Message):
    """Guruhda kelgan xabarlarni qayta ishlash va guruh balansiga yozish."""
    chat_id = message.chat.id
    user_id = message.from_user.id
    text = message.text

    # Bu guruh bizga bog'langanmi?
    group = await get_group_by_chat_id(chat_id)
    if not group:
        return  # Bizga tegishli emas

    # Bu foydalanuvchi guruh a'zosimi?
    is_member = any(m["telegram_id"] == user_id for m in group.get("members", []))
    if not is_member:
        return  # A'zo emas, skip

    # AI orqali tranzaksiyani tahlil qilish
    user = await get_user(user_id)
    language = user.get("language", "uz")
    current_date = __import__("datetime").datetime.now().strftime("%Y-%m-%d")

    custom_cats = await get_custom_categories(user_id)
    custom_cats_list = [{"emoji": c["emoji"], "name": c["name"], "type": c["type"]} for c in custom_cats] if custom_cats else None
    user_context = await get_user_financial_context(user_id)
    recent_txs = await get_recent_transactions_context(user_id)
    habits = await get_user_habits(user_id)

    try:
        data = await gemini_service.parse_transaction(
            text=text,
            current_date_str=current_date,
            language=language,
            custom_categories=custom_cats_list,
            user_id=user_id,
            user_context=user_context,
            recent_txs=recent_txs,
            habits=habits
        )
    except GeminiServerError:
        await message.answer("⏳")
        import asyncio
        asyncio.create_task(handle_queued_group_transaction(
            message, text, current_date, language, custom_cats_list, user_id, user_context, recent_txs, habits, group, user
        ))
        return
    except Exception as e:
        logger.error(f"AI error in group {chat_id}: {e}")
        return

    await process_group_parsed_data(data, message, user, group, current_date)


async def handle_queued_group_transaction(message, text, current_date, language, custom_cats_list, user_id, user_context, recent_txs, habits, group, user):
    import asyncio
    while True:
        try:
            data = await gemini_service.parse_transaction(
                text=text,
                current_date_str=current_date,
                language=language,
                custom_categories=custom_cats_list,
                user_id=user_id,
                user_context=user_context,
                recent_txs=recent_txs,
                habits=habits
            )
            break
        except GeminiServerError:
            await asyncio.sleep(30)
        except Exception as e:
            logger.error(f"AI error in queued group transaction: {e}")
            return
            
    await process_group_parsed_data(data, message, user, group, current_date)


async def process_group_parsed_data(data: dict, message: Message, user: dict, group: dict, current_date: str):
    # Faqat tranzaksiyalarni qayta ishlaymiz (chat/error ni skip)
    if data.get("intent") in ("error", "chat") or data.get("unclear"):
        return

    transactions = data.get("transactions", [])
    if not transactions:
        return

    user_name = user.get("full_name", "Noma'lum")

    for tx in transactions:
        tx_type = tx.get("transaction_type", tx.get("type"))
        amount = float(tx.get("amount", 0))
        currency = tx.get("currency", "UZS").upper()
        category = tx.get("category", "📋 Boshqa")
        description = tx.get("description", "")

        if tx_type in ("kirim", "chiqim"):
            # Guruh tranzaksiyasini saqlash
            await insert_group_transaction(group["id"], {
                "telegram_id": user_id,
                "type": tx_type,
                "amount": amount,
                "currency": currency,
                "date": current_date,
                "description": description,
                "category": category,
                "member_name": user_name,
                "affects_balance": True,
            })

            # Guruh balansini yangilash (shaxsiy balansga ta'sir QILMAYDI)
            new_bal = await update_group_balance(
                group["id"], currency, amount, is_income=(tx_type == "kirim")
            )

            sign = "+" if tx_type == "kirim" else "-"
            fmt_amount = f"{int(amount):,}".replace(",", " ")
            fmt_bal = f"{int(new_bal):,}".replace(",", " ")

            await message.reply(
                f"✅ Guruh balansiga yozildi!\n\n"
                f"👤 {user_name}\n"
                f"{'💰 Kirim' if tx_type == 'kirim' else '💸 Chiqim'}: {sign}{fmt_amount} {currency}\n"
                f"📝 {category}\n"
                f"━━━━━━━━━━━━━━━━\n"
                f"💼 Guruh balans: {fmt_bal} {currency}"
            )
