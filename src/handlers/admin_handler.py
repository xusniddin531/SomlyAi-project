"""
Admin operations handler.
Commands:
- /stats
- /user [id]
- /admin [id]
- /remove_admin [id]
- /channels
- /add_channel [link] [nomi]
- /setchannel [num] [link_yoki_username]
- /remove_channel [link]
- /send (fsm: waiting for message, then confirm)
- /setwebapp [link]
- /ban [id]
- /unban [id]
"""

import asyncio
import logging
from aiogram import Router, Bot, F
from aiogram.filters import Command
from aiogram.types import Message, MenuButtonWebApp, WebAppInfo, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

class BroadcastState(StatesGroup):
    waiting_for_message = State()

class ChannelAdminStates(StatesGroup):
    waiting_for_add_link = State()
    waiting_for_add_name = State()
    waiting_for_change_selection = State()
    waiting_for_change_link = State()
    waiting_for_change_name = State()
from src.database import (
    is_admin, add_admin, remove_admin,
    add_channel, remove_channel, get_all_channels, update_channel_by_index,
    get_bot_statistics, get_user_full_stats, users_collection,
    set_user_blacklist
)
from src.config import ADMIN_ID
from src.services.error_handler import handle_error, ErrorType

router = Router()
logger = logging.getLogger(__name__)

class BroadcastState(StatesGroup):
    waiting_for_message = State()

async def check_admin(user_id: int, message_or_cb, bot: Bot) -> bool:
    """Check if user is admin. If not, alert real admin and reject."""
    if await is_admin(user_id):
        return True
    
    # Reject message
    if isinstance(message_or_cb, Message):
        await message_or_cb.answer("❌ Ruxsat yo'q.")
        command = message_or_cb.text
    else:
        await message_or_cb.answer("❌ Ruxsat yo'q.", show_alert=True)
        command = message_or_cb.data
        
    # Alert real admin
    await handle_error(
        bot, 
        ErrorType.TELEGRAM_GENERAL, 
        f"Unauthorized admin access attempt by User ID: {user_id}\nCommand: {command}", 
        user_id
    )
    return False

@router.message(Command("stats"))
async def cmd_stats(message: Message, bot: Bot):
    if not await check_admin(message.from_user.id, message, bot): return
    stats = await get_bot_statistics()
    text = (
        f"📊 <b>Somly AI statistikasi:</b>\n"
        f"👥 Jami foydalanuvchilar: {stats['total_users']:,}\n"
        f"📅 Bugun qo'shilganlar: {stats['today_users']:,}\n"
        f"🔄 Aktiv (7 kun): {stats['active_users']:,}\n"
        f"💬 Bugungi xabarlar: {stats['today_messages']:,}\n"
        f"📊 Bugungi tranzaksiyalar: {stats['today_txs']:,}\n"
        f"💰 Jami tranzaksiyalar: {stats['total_txs']:,}\n"
        f"🌍 Tillar: {stats['langs']}"
    )
    await message.answer(text, parse_mode="HTML")

@router.message(Command("user"))
async def cmd_user(message: Message, bot: Bot):
    if not await check_admin(message.from_user.id, message, bot): return
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Xato! Format: /user [telegram_id]")
        return
    try:
        user_id = int(args[1])
        u_stats = await get_user_full_stats(user_id)
        if not u_stats:
            await message.answer("❌ Foydalanuvchi topilmadi.")
            return
            
        b_uzs = u_stats['balances'].get('UZS', {}).get('amount', 0)
        b_usd = u_stats['balances'].get('USD', {}).get('amount', 0)
        blacklisted = "Ha 🚫" if u_stats.get("is_blacklisted") else "Yo'q"
        
        text = (
            f"👤 Foydalanuvchi: {u_stats['full_name']}\n"
            f"📱 Telefon: {u_stats['phone']}\n"
            f"📅 Ro'yxat: {u_stats['created_at']}\n"
            f"💰 Balans: {b_uzs:,} UZS | {b_usd:,} USD\n"
            f"📊 Tranzaksiyalar: {u_stats['tx_count']}\n"
            f"🔄 Oxirgi faollik: {u_stats['last_active']}\n"
            f"🚫 Qora ro'yxatda: {blacklisted}"
        )
        await message.answer(text)
    except ValueError:
        await message.answer("❌ ID faqat raqamlardan iborat bo'lishi kerak.")

@router.message(Command("ban"))
async def cmd_ban(message: Message, bot: Bot):
    if not await check_admin(message.from_user.id, message, bot): return
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Xato! Format: /ban [telegram_id]")
        return
    try:
        user_id = int(args[1])
        if await set_user_blacklist(user_id, True):
            await message.answer(f"✅ User {user_id} qora ro'yxatga kiritildi. Endi bot undan xabar qabul qilmaydi.")
        else:
            await message.answer("❌ Foydalanuvchi topilmadi.")
    except ValueError:
        await message.answer("❌ ID faqat raqamlardan iborat bo'lishi kerak.")

@router.message(Command("unban"))
async def cmd_unban(message: Message, bot: Bot):
    if not await check_admin(message.from_user.id, message, bot): return
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Xato! Format: /unban [telegram_id]")
        return
    try:
        user_id = int(args[1])
        if await set_user_blacklist(user_id, False):
            await message.answer(f"✅ User {user_id} qora ro'yxatdan chiqarildi.")
        else:
            await message.answer("❌ Foydalanuvchi topilmadi.")
    except ValueError:
        await message.answer("❌ ID faqat raqamlardan iborat bo'lishi kerak.")

@router.message(Command("channels"))
async def cmd_channels(message: Message, bot: Bot):
    if not await check_admin(message.from_user.id, message, bot): return
    channels = await get_all_channels()
    if not channels:
        await message.answer("Hozircha kanallar yo'q.")
        return
        
    msg = "<b>Hozirgi kanallar:</b>\n"
    for idx, c in enumerate(channels, 1):
        msg += f"{idx}. {c['name']} ({c['link']})\n"
    
    msg += "\nO'zgartirish: <code>/setchannel 1 @yangi_kanal</code>"
    await message.answer(msg, parse_mode="HTML")

@router.message(Command("setchannel"))
async def cmd_setchannel(message: Message, bot: Bot):
    if not await check_admin(message.from_user.id, message, bot): return
    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        await message.answer("Xato! Format: /setchannel [tartib_raqami] [@kanal_yoki_link] [Kanal nomi - ixtiyoriy]")
        return
        
    try:
        index = int(args[1]) - 1
        new_link = args[2]
        new_name = "Yangi kanal" if len(args) == 3 else args[2]
        
        if not new_link.startswith("http") and not new_link.startswith("@"):
             await message.answer("Link @ bilan yoki https bilan boshlanishi kerak.")
             return
             
        channels = await get_all_channels()
        if index < 0 or index >= len(channels):
             await message.answer("❌ Bunday raqamli kanal yo'q. /channels orqali raqamlarni ko'ring.")
             return
             
        if await update_channel_by_index(index, new_link, new_name):
             await message.answer(f"✅ {index+1}-kanal o'zgartirildi: {new_link}")
        else:
             await message.answer("❌ Xatolik yuz berdi.")
             
    except ValueError:
        await message.answer("❌ Tartib raqami son bo'lishi kerak.")

async def _get_valid_webapp_url():
    """Webapp URL ni olish. Noto'g'ri bo'lsa ngrok dan avtomatik aniqlashga harakat."""
    from src.database import get_webapp_url, set_webapp_url
    url = await get_webapp_url()

    # URL haqiqiy HTTPS URL ekanligini tekshirish
    if url and url.startswith("https://") and "." in url and "YOUR_" not in url.upper():
        return url

    # Ngrok dan avtomatik aniqlash
    try:
        import aiohttp
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=3)) as session:
            async with session.get("http://127.0.0.1:4040/api/tunnels") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    for tunnel in data.get("tunnels", []):
                        pub_url = tunnel.get("public_url", "")
                        if pub_url.startswith("https://"):
                            await set_webapp_url(pub_url)
                            return pub_url
    except Exception:
        pass

    return None


@router.message(Command("admin"))
async def cmd_admin_panel(message: Message, bot: Bot):
    if not await check_admin(message.from_user.id, message, bot): return

    base_url = await _get_valid_webapp_url()

    # Agar URL o'rnatilmagan yoki noto'g'ri bo'lsa
    if not base_url:
        await message.answer(
            "⚠️ <b>WebApp URL o'rnatilmagan yoki noto'g'ri!</b>\n\n"
            "Admin panelga kirish uchun avval URL o'rnating:\n"
            "<code>/setwebapp https://NGROK_URL</code>\n\n"
            "📌 Ngrok URL ni ngrok terminalidan oling\n"
            "(masalan: https://abc123.ngrok-free.app)",
            parse_mode="HTML"
        )
        return

    admin_url = f"{base_url.rstrip('/')}/admin"

    try:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔐 Admin panelga kirish", web_app=WebAppInfo(url=admin_url))]
        ])
        await message.answer("🛠 <b>Somly AI Admin Paneli</b>\n\nMini App orqali botni boshqarish uchun quyidagi tugmani bosing:", reply_markup=kb, parse_mode="HTML")
    except Exception as e:
        await message.answer(
            f"❌ URL xatosi: <code>{admin_url}</code>\n\n"
            f"To'g'ri URL o'rnating:\n<code>/setwebapp https://NGROK_URL</code>",
            parse_mode="HTML"
        )


@router.message(Command("pin_change"))
async def cmd_pin_change(message: Message, bot: Bot):
    if not await check_admin(message.from_user.id, message, bot): return
    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        await message.answer("Format: /pin_change [eski_pin] [yangi_pin]\nMisol: /pin_change 1973 1234")
        return
    
    old_pin = args[1]
    new_pin = args[2]
    
    if len(new_pin) != 4 or not new_pin.isdigit():
        await message.answer("❌ Yangi PIN faqat 4 ta raqamdan iborat bo'lishi kerak.")
        return
        
    from src.database import db
    settings = await db["admin_settings"].find_one({"key": "pin"})
    stored_pin = settings["value"] if settings else "1973"
    
    if old_pin != stored_pin:
        await message.answer("❌ Eski PIN noto'g'ri.")
        return
        
    await db["admin_settings"].update_one(
        {"key": "pin"},
        {"$set": {"key": "pin", "value": new_pin}},
        upsert=True
    )
    await message.answer("✅ PIN muvaffaqiyatli o'zgartirildi!")


@router.message(Command("set_admin"))
async def cmd_add_admin(message: Message, bot: Bot):
    if not await check_admin(message.from_user.id, message, bot): return
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Xato! Format: /set_admin [telegram_id]")
        return
    try:
        new_admin_id = int(args[1])
        if await add_admin(new_admin_id):
            await message.answer(f"✅ {new_admin_id} adminlar ro'yxatiga qo'shildi.")
        else:
            await message.answer("❌ Bu ID allaqachon admin yoki xatolik.")
    except ValueError:
        await message.answer("❌ ID faqat raqamlardan iborat bo'lishi kerak.")


@router.message(Command("remove_admin"))
async def cmd_remove_admin(message: Message, bot: Bot):
    if not await check_admin(message.from_user.id, message, bot): return
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Xato! Format: /remove_admin [telegram_id]")
        return
    try:
        target_id = int(args[1])
        if await remove_admin(target_id):
            await message.answer(f"✅ {target_id} adminlikdan o'chirildi.")
        else:
            await message.answer("❌ Bosh adminni o'chirib bo'lmaydi yoki bunday admin yo'q.")
    except ValueError:
        await message.answer("❌ ID faqat raqamlardan iborat bo'lishi kerak.")


@router.message(Command("add_channel"))
async def cmd_add_channel(message: Message, state: FSMContext, bot: Bot):
    """Format: /add_channel @kanal_username [Tugma Nomi]
    Yoki: /add_channel https://t.me/kanal_nomi [Tugma Nomi]
    Agar tugma nomi berilmasa, kanal username'i ishlatiladi."""
    if not await check_admin(message.from_user.id, message, bot): return
    
    args = message.text.split(maxsplit=2)
    if len(args) < 2:
        await message.answer(
            "📢 <b>Kanal qo'shish:</b>\n\n"
            "Format: <code>/add_channel @kanal Tugma Nomi</code>\n"
            "Masalan: <code>/add_channel @Somly_AI Somly AI Rasmiy</code>\n\n"
            "Tugma nomi ixtiyoriy — berilmasa kanal linki yoziladi.",
            parse_mode="HTML"
        )
        return
    
    link = args[1].strip()
    name = args[2].strip() if len(args) > 2 else link
    
    # Link formatini to'g'rilash
    if link.startswith("@"):
        full_link = f"https://t.me/{link[1:]}"
    elif link.startswith("https://"):
        full_link = link
    else:
        await message.answer("❌ Link <code>@kanal</code> yoki <code>https://t.me/...</code> formatida bo'lishi kerak.", parse_mode="HTML")
        return
    
    if await add_channel(full_link, name):
        # Bot admin ekanligini tekshirish
        chat_identifier = f"@{link[1:]}" if link.startswith("@") else link
        admin_warning = ""
        try:
            bot_member = await bot.get_chat_member(chat_id=chat_identifier, user_id=(await bot.get_me()).id)
            if bot_member.status not in ["administrator", "creator"]:
                admin_warning = "\n\n⚠️ <b>Diqqat:</b> Bot bu kanalda admin emas! Obuna tekshiruvi ishlamaydi."
        except Exception:
            admin_warning = "\n\n⚠️ <b>Diqqat:</b> Bot bu kanalga kirish imkoniga ega emas! Admin qilib qo'ying."
        
        await message.answer(
            f"✅ Kanal muvaffaqiyatli qo'shildi!\n"
            f"📢 Nom: {name}\n"
            f"🔗 Link: {full_link}{admin_warning}",
            parse_mode="HTML"
        )
    else:
        await message.answer("❌ Bu kanal allaqachon qo'shilgan.")


@router.message(Command("edit_channel"))
async def cmd_edit_channel(message: Message, bot: Bot):
    """Format: /edit_channel 1 @yangi_kanal [Yangi Nom]"""
    if not await check_admin(message.from_user.id, message, bot): return
    
    args = message.text.split(maxsplit=3)
    if len(args) < 3:
        channels = await get_all_channels()
        if not channels:
            await message.answer("Hozircha kanallar yo'q. Avval /add_channel orqali kanal qo'shing.")
            return
        
        msg = "📢 <b>Kanal o'zgartirish:</b>\n\n"
        msg += "Format: <code>/edit_channel [raqam] @yangi_kanal [Yangi Nom]</code>\n\n"
        msg += "<b>Hozirgi kanallar:</b>\n"
        for idx, c in enumerate(channels, 1):
            msg += f"{idx}. {c['name']} ({c['link']})\n"
        await message.answer(msg, parse_mode="HTML")
        return
    
    try:
        index = int(args[1]) - 1
        new_link = args[2].strip()
        new_name = args[3].strip() if len(args) > 3 else new_link
        
        # Link formatini to'g'rilash
        if new_link.startswith("@"):
            full_link = f"https://t.me/{new_link[1:]}"
        elif new_link.startswith("https://"):
            full_link = new_link
        else:
            await message.answer("❌ Link <code>@kanal</code> yoki <code>https://t.me/...</code> formatida bo'lishi kerak.", parse_mode="HTML")
            return
        
        channels = await get_all_channels()
        if index < 0 or index >= len(channels):
            await message.answer(f"❌ Bunday raqamli kanal yo'q. Jami {len(channels)} ta kanal bor.")
            return
        
        if await update_channel_by_index(index, full_link, new_name):
            await message.answer(f"✅ {index+1}-kanal o'zgartirildi!\n📢 Nom: {new_name}\n🔗 Link: {full_link}")
        else:
            await message.answer("❌ Xatolik yuz berdi.")
    except ValueError:
        await message.answer("❌ Tartib raqami son bo'lishi kerak.")


@router.message(Command("remove_channel"))
async def cmd_remove_channel(message: Message, bot: Bot):
    """Format: /remove_channel @kanal_username
    Yoki: /remove_channel https://t.me/kanal_nomi"""
    if not await check_admin(message.from_user.id, message, bot): return
    
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        channels = await get_all_channels()
        if not channels:
            await message.answer("Hozircha kanallar yo'q.")
            return
        
        msg = "📢 <b>Kanal o'chirish:</b>\n\n"
        msg += "Format: <code>/remove_channel @kanal</code>\n\n"
        msg += "<b>Hozirgi kanallar:</b>\n"
        for idx, c in enumerate(channels, 1):
            msg += f"{idx}. {c['name']} ({c['link']})\n"
        await message.answer(msg, parse_mode="HTML")
        return
    
    link = args[1].strip()
    
    # Link formatini to'g'rilash
    if link.startswith("@"):
        full_link = f"https://t.me/{link[1:]}"
    elif link.startswith("https://"):
        full_link = link
    else:
        await message.answer("❌ Link <code>@kanal</code> yoki <code>https://t.me/...</code> formatida bo'lishi kerak.", parse_mode="HTML")
        return
    
    if await remove_channel(full_link):
        await message.answer(f"✅ Kanal o'chirildi: {full_link}")
    else:
        await message.answer(f"❌ <code>{full_link}</code> topilmadi. /channels orqali hozirgi kanallarni ko'ring.", parse_mode="HTML")


# ─── BROADCAST SYSTEM ───

@router.message(Command("send"))
async def cmd_send(message: Message, state: FSMContext, bot: Bot):
    if not await check_admin(message.from_user.id, message, bot): return
    await state.set_state(BroadcastState.waiting_for_message)
    await message.answer("📣 Yuboriladigan xabarni (rasm, video, matn) yuboring.\nBekor qilish uchun /cancel bosing.")


@router.message(BroadcastState.waiting_for_message)
async def process_broadcast_message(message: Message, state: FSMContext, bot: Bot):
    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Xabar yuborish bekor qilindi.")
        return

    await state.clear()
    
    total_users = await users_collection.count_documents({"is_active": True})
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Yuborish", callback_data="confirm_send"),
            InlineKeyboardButton(text="❌ Bekor", callback_data="cancel_send")
        ]
    ])
    
    await state.update_data(broadcast_msg_id=message.message_id, broadcast_chat_id=message.chat.id, total_users=total_users)
    
    await message.answer(
        f"{total_users} ta foydalanuvchiga yuborilsinmi?\n\n<i>Yuborayotgan xabaringiz yuqorida.</i>",
        reply_markup=kb, parse_mode="HTML"
    )

@router.callback_query(F.data == "confirm_send")
async def confirm_send_callback(callback: CallbackQuery, state: FSMContext, bot: Bot):
    if not await check_admin(callback.from_user.id, callback, bot): return
        
    data = await state.get_data()
    msg_id = data.get("broadcast_msg_id")
    chat_id = data.get("broadcast_chat_id")
    total_users = data.get("total_users", 0)
    
    if not msg_id:
        await callback.message.edit_text("❌ Xato! Xabar topilmadi.")
        return
        
    await callback.message.edit_text(f"⏳ Yuborilmoqda: 0 / {total_users}")
    
    cursor = users_collection.find({"is_active": True})
    users = await cursor.to_list(length=100000)
    
    success_count = 0
    fail_count = 0
    
    from src.services.error_handler import safe_send_message
    
    for i, user in enumerate(users, 1):
        try:
            await bot.copy_message(
                chat_id=user["telegram_id"],
                from_chat_id=chat_id,
                message_id=msg_id
            )
            success_count += 1
        except Exception:
            fail_count += 1
            
        if i % 50 == 0 or i == total_users:
            try:
                await callback.message.edit_text(f"⏳ Yuborildi: {success_count} / {total_users}\n(Xato: {fail_count})")
            except Exception:
                pass
                
        await asyncio.sleep(0.05)
            
    await callback.message.edit_text(f"✅ Tarqatish yakunlandi!\n\nJo'natildi: {success_count} ta\nXato: {fail_count} ta")
    await state.clear()

@router.callback_query(F.data == "cancel_send")
async def cancel_send_callback(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("❌ Yuborish bekor qilindi.")
    await state.clear()


@router.message(Command("setwebapp"))
async def cmd_setwebapp(message: Message, bot: Bot):
    if not await check_admin(message.from_user.id, message, bot): return
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Xato! Format: /setwebapp [link]\nMasalan: /setwebapp https://...ngrok-free.app")
        return
    url = args[1].strip()
    if not url.startswith("https://"):
        await message.answer("❌ Xato! Link 'https://' bilan boshlanishi shart.")
        return
    if "YOUR_" in url.upper() or "." not in url.split("://")[1]:
        await message.answer("❌ Bu haqiqiy URL emas! Ngrok terminalidan URL ni nusxalab yuboring.")
        return
        
    try:
        from src.database import set_webapp_url
        await set_webapp_url(url)
        await bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(text="Ochish", web_app=WebAppInfo(url=url))
        )
        await message.answer(f"✅ Web App tugmasi ('Ochish') muvaffaqiyatli o'rnatildi!\nLink: {url}")
    except Exception as e:
        await message.answer(f"❌ Xatolik yuz berdi: {str(e)}")


# /web, /teach, /knowledge, /unteach, /editteach commandlari OLIB TASHLANDI
# Endi bularning hammasi Admin Mini App orqali boshqariladi:
#   • /web        → Admin Mini App'ning o'zi (/admin route)
#   • /teach      → Mini App'da "Bilimlar bazasi" sahifasi (REST: POST /api/admin/knowledge)
#   • /knowledge  → Mini App'da "Bilimlar bazasi" sahifasi (REST: GET /api/admin/knowledge)
#   • /unteach    → Mini App'da bilim kartochkasidagi "O'chirish" tugmasi (REST: DELETE)
#   • /editteach  → Mini App'da bilim kartochkasidagi "Tahrirlash" tugmasi (REST: PUT)
