"""
Registration handler — Name + Gender Detection + Phone collection.

Onboarding Flow Steps (handled here):
- STEP 3: Name input (text or voice) → AI gender detection
- STEP 4: Phone number via contact sharing
- STEP 5: Channel subscription (handled by middleware)
- STEP 6: First transaction prompt
"""

import os
import logging
from aiogram import Router, F, Bot
from aiogram.types import (
    Message, CallbackQuery,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.fsm.context import FSMContext
from src.states import RegistrationStates
from src.database import (
    get_user, update_user_name, update_user_phone,
    update_user_gender, get_all_channels, update_user_channels_joined
)
from src.services.gemini_service import gemini_service
from src.services.i18n import t

router = Router()
logger = logging.getLogger(__name__)


# ═══════════════════════════════════════
# JINS ANIQLASH FUNKSIYASI
# ═══════════════════════════════════════

# O'zbek erkak ismlari ro'yxati
MALE_NAMES = {
    "jasur", "sardor", "husan", "bobur", "sherzod", "ulugbek", "anvar",
    "behruz", "davron", "eldor", "farhod", "gafur", "hamid", "ilhom",
    "jamshid", "kamoliddin", "laziz", "mansur", "nodir", "oybek",
    "pulat", "qodir", "rustam", "sanjar", "tohir", "umid", "vohid",
    "xurshid", "yusuf", "zafar", "abdulloh", "akbar", "alisher",
    "baxtiyor", "dilshod", "erkin", "farrux", "giyos", "hasan",
    "ismoil", "javlon", "kamol", "lochin", "mirzo", "nuriddin",
    "obid", "parviz", "ravshan", "saidakbar", "temur", "ulfat",
    "valijon", "xasan", "yorqin", "zahid", "aziz", "bahodir",
    "doniyor", "elyor", "furqat", "hayot", "islom", "jaloliddin",
    "komil", "lutfillo", "muxammad", "muhammad", "narzullo",
    "ozodbek", "pahlavon", "rauf", "suxrob", "toxir", "umar",
    "valijon", "xasan", "yorqin", "zahid", "aziz", "bahodir",
}

# O'zbek ayol ismlari ro'yxati
FEMALE_NAMES = {
    "dilnoza", "gulnora", "madina", "malika", "nilufar", "nodira",
    "ozoda", "parizod", "ra'no", "sarvinoz", "shahlo", "zulfiya",
    "barno", "dilorom", "feruza", "gavhar", "hulkar", "iroda",
    "kamola", "lola", "mohira", "nafisa", "odinaxon", "parvin",
    "robiya", "saodat", "tursunoy", "umida", "vasilaxon", "xurshida",
    "yulduz", "ziyoda", "aziza", "barcha", "charos", "dildora",
    "fotima", "gulsanam", "hilola", "irodaxon", "komila", "lobar",
    "maftuna", "nasiba", "oydin", "parvina", "sabohat", "zilola",
}


def detect_gender_by_name(name: str) -> str:
    """Ismdan jinsni aniqlash (local, AI ga murojaat qilmasdan)."""
    name_lower = name.lower().strip().split()[0] if name else ""
    if name_lower in MALE_NAMES:
        return "male"
    if name_lower in FEMALE_NAMES:
        return "female"
    # Qo'shimcha qoidalar
    if name_lower.endswith(("xon", "oy", "gul", "noz", "niso")):
        return "female"
    if name_lower.endswith(("bek", "boy", "jon", "din", "llo")):
        return "male"
    return "unknown"


# ═══════════════════════════════════════
# 3-QADAM: ISM QABUL QILISH (matn)
# ═══════════════════════════════════════
@router.message(RegistrationStates.waiting_for_name, F.text)
async def process_name_text(message: Message, state: FSMContext):
    name = message.text.strip()

    # Agar buyruq yuborsa — e'tiborsiz qoldiramiz
    if name.startswith("/"):
        return

    user_id = message.from_user.id
    user = await get_user(user_id)
    lang = user.get("language", "uz")

    username = message.from_user.username
    await update_user_name(user_id, name, username=username)
    
    # ════════════════════════════════════════════
    # JINS ANIQLASH (AI ismdan)
    # ════════════════════════════════════════════
    gender = await gemini_service.detect_gender(name)
    await update_user_gender(user_id, gender)
    logger.info(f"Gender detected for '{name}': {gender}")

    # "🤝 Tanishganimdan xursandman, [Ism]!"
    await message.answer(t(lang, "greeting_after_name", name=name))
    
    # ════════════════════════════════════════════
    # 4-QADAM: TELEFON RAQAM SO'RASH
    # ════════════════════════════════════════════
    await state.set_state(RegistrationStates.waiting_for_contact)
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=t(lang, "share_contact_btn"), request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await message.answer(t(lang, "ask_contact"), reply_markup=keyboard)


# ═══════════════════════════════════════
# 3-QADAM: ISM QABUL QILISH (ovozli)
# ═══════════════════════════════════════
@router.message(RegistrationStates.waiting_for_name, F.voice)
async def process_name_voice(message: Message, state: FSMContext, bot: Bot):
    user_id = message.from_user.id
    user = await get_user(user_id)
    lang = user.get("language", "uz")

    status_msg = await message.answer("🎤 ...")

    file_id = message.voice.file_id
    file = await bot.get_file(file_id)
    file_path = file.file_path

    os.makedirs("temp", exist_ok=True)
    local_path = f"temp/{file_id}.ogg"

    try:
        await bot.download_file(file_path, local_path)
        transcribed = await gemini_service.transcribe_audio_with_retry(local_path)
        # AI orqali faqat ismni ajratib olish
        name = await gemini_service.extract_name(transcribed)

        if not name or len(name) < 2:
            name = transcribed.strip()

        username = message.from_user.username
        await update_user_name(user_id, name, username=username)
        
        # Jins aniqlash (AI orqali)
        gender = await gemini_service.detect_gender(name)
        await update_user_gender(user_id, gender)
        logger.info(f"Gender detected (voice) for '{name}': {gender}")
        
        await status_msg.delete()

        # "🤝 Tanishganimdan xursandman, [Ism]!"
        await message.answer(t(lang, "greeting_after_name", name=name))
        
        # 4-QADAM: TELEFON RAQAM SO'RASH
        await state.set_state(RegistrationStates.waiting_for_contact)
        keyboard = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text=t(lang, "share_contact_btn"), request_contact=True)]],
            resize_keyboard=True,
            one_time_keyboard=True,
        )
        await message.answer(t(lang, "ask_contact"), reply_markup=keyboard)

    except Exception:
        error_msgs = {
            "uz": "❌ Ovozni tahlil qilib bo'lmadi. Iltimos, ismingizni matn sifatida yozing.",
            "ru": "❌ Не удалось распознать голос. Пожалуйста, напишите имя текстом.",
            "en": "❌ Could not process voice. Please type your name instead."
        }
        await status_msg.edit_text(error_msgs.get(lang, error_msgs["uz"]))
    finally:
        if os.path.exists(local_path):
            os.remove(local_path)


# ═══════════════════════════════════════
# 4-QADAM: CONTACT QABUL QILISH
# ═══════════════════════════════════════
@router.message(RegistrationStates.waiting_for_contact, F.contact)
async def process_contact(message: Message, state: FSMContext):
    user_id = message.from_user.id
    phone = message.contact.phone_number
    user = await get_user(user_id)
    lang = user.get("language", "uz")
    name = user.get("full_name", "")

    await update_user_phone(user_id, phone)
    
    # Referral tracking
    data = await state.get_data()
    referrer_id = data.get("referrer_id")
    if referrer_id:
        from src.database import track_referral, referrals_collection
        success = await track_referral(referrer_id, user_id)
        if success:
            try:
                from src.bot import bot
                stats = await referrals_collection.count_documents({"referrer_id": referrer_id})
                await bot.send_message(
                    chat_id=referrer_id,
                    text=f"🎉 Do'stingiz Somly AI ga qo'shildi!\nEndi siz {stats} kishini taklif qildingiz 👍"
                )
            except Exception as e:
                logger.warning(f"Failed to notify referrer {referrer_id}: {e}")

    await state.clear()
    
    # ═══ SEGMENTATSIYA BOSHLANISHI ═══
    # Onboarding tugagandan keyin 1-4 soat ichida birinchi savol yuboriladi
    from src.database import start_segmentation
    await start_segmentation(user_id)
    
    # Reply keyboard olib tashlanadi
    # "🎉 Tabriklayman, ro'yxatdan o'tib oldingiz!"
    await message.answer(
        t(lang, "registration_done"),
        reply_markup=ReplyKeyboardRemove()
    )
    
    # ════════════════════════════════════════════
    # 5-QADAM: KANAL OBUNASI TEKSHIRUVI
    # ════════════════════════════════════════════
    channels = await get_all_channels()
    
    if channels:
        # Get webapp url for redirect
        from src.database import db
        settings = await db["admin_settings"].find_one({"key": "webapp_url"})
        base_url = settings["value"] if settings else "https://somly.ai"
        base_url = base_url.rstrip("/")
        
        # "Botdan bepul foydalanish uchun quyidagi kanalga obuna bo'ling 👇"
        buttons = []
        for ch in channels:
            import urllib.parse
            encoded_link = urllib.parse.quote(ch['link'])
            redirect_url = f"{base_url}/api/redirect?c={encoded_link}&u={user_id}"
            buttons.append([InlineKeyboardButton(text=f"📢 {ch['name']}", url=redirect_url)])
        
        buttons.append([InlineKeyboardButton(
            text=t(lang, "channel_check_btn"),
            callback_data="check_sub_onboarding"
        )])
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        
        await message.answer(
            t(lang, "channel_subscribe"),
            reply_markup=keyboard
        )
    else:
        # Kanallar yo'q — to'g'ridan-to'g'ri 6-qadamga o'tish
        await update_user_channels_joined(user_id, True)
        await _send_first_transaction_prompt(message, lang)


# ═══════════════════════════════════════
# 5-QADAM: KANAL OBUNASI TEKSHIRISH CALLBACK
# ═══════════════════════════════════════
@router.callback_query(lambda c: c.data == "check_sub_onboarding")
async def check_subscription_onboarding(callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    user = await get_user(user_id)
    lang = user.get("language", "uz")
    bot = callback_query.bot
    
    channels = await get_all_channels()
    not_subscribed = []
    subscribed_channels = []
    
    for ch in channels:
        link = ch["link"]
        chat_identifier = link
        if "t.me/" in link and "+" not in link:
            username = link.split("t.me/")[1].split("/")[0]
            chat_identifier = f"@{username}"
        
        try:
            member = await bot.get_chat_member(chat_id=chat_identifier, user_id=user_id)
            if member.status in ["left", "kicked", "restricted"]:
                not_subscribed.append(ch)
            else:
                subscribed_channels.append(ch)
        except Exception as e:
            logger.warning(f"Sub check failed for {chat_identifier}: {e}")
            # Agar tekshirib bo'lmasa, skip qilamiz
            subscribed_channels.append(ch)
    
    if not_subscribed:
        # "❌ Hali obuna bo'lmadingiz. Iltimos obuna bo'ling 🙏"
        await callback_query.answer(
            t(lang, "channel_not_subscribed"),
            show_alert=True
        )
    else:
        # OBUNA MUVAFFAQIYATLI!
        from src.database import confirm_channel_subscription
        for ch in subscribed_channels:
            await confirm_channel_subscription(user_id, ch["link"])
            
        await update_user_channels_joined(user_id, True)
        await callback_query.message.delete()
        
        # "✅ Zo'r! Endi bemalol foydalanishingiz mumkin! 🎉"
        await callback_query.message.answer(t(lang, "channel_subscribed"))
        
        # ════════════════════════════════════════════
        # 6-QADAM: BIRINCHI TRANZAKSIYA TAKLIFI
        # ════════════════════════════════════════════
        await _send_first_transaction_prompt(callback_query.message, lang)
        await callback_query.answer()


async def _send_first_transaction_prompt(message: Message, lang: str):
    """
    6-QADAM: Birinchi tranzaksiya taklifi.
    """
    from src.handlers.menu_handler import get_main_keyboard
    kbd = await get_main_keyboard(lang)
    
    # "Botga quyidagi xabarni ovozli yoki matn ko'rinishida kiriting:
    #  💬 'Fastfoodga 40,000, taksiga esa 15,000 so'm sarfladim'
    #  Shunday oddiy! 😊"
    await message.answer(
        t(lang, "first_transaction_prompt"),
        reply_markup=kbd
    )


# ═══════════════════════════════════════
# CONTACT BERMAGAN — MATN YOZGAN
# ═══════════════════════════════════════
@router.message(RegistrationStates.waiting_for_contact, F.text)
async def process_contact_text_fallback(message: Message):
    if message.text.startswith("/"):
        return
    user_id = message.from_user.id
    user = await get_user(user_id)
    lang = user.get("language", "uz")

    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=t(lang, "share_contact_btn"), request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await message.answer(t(lang, "contact_required"), reply_markup=keyboard)


# ═══════════════════════════════════════
# CONTACT BERMAGAN — OVOZ YUBORGAN
# ═══════════════════════════════════════
@router.message(RegistrationStates.waiting_for_contact, F.voice)
async def process_contact_voice_fallback(message: Message):
    user_id = message.from_user.id
    user = await get_user(user_id)
    lang = user.get("language", "uz")

    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=t(lang, "share_contact_btn"), request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await message.answer(t(lang, "contact_required"), reply_markup=keyboard)
