"""
Segment Handler — Foydalanuvchi segmentatsiya savollariga javoblarni qabul qilish.

Savollar tartibi:
  Stage 0 → Yosh (age_group)
  Stage 1 → Joylashuv (country, region, timezone)
  Stage 2 → Tugallangan

Qiziqishlar (interests) alohida — tranzaksiya asosida avtomatik kuzatiladi.
"""

import logging
from aiogram import Router, F
from aiogram.types import (
    CallbackQuery, Message,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from aiogram.fsm.context import FSMContext
from src.database import (
    get_user, update_segment_data, complete_segmentation,
    add_user_interest, add_interest_query,
)
from src.states import SegmentationStates
from src.services.i18n import t

logger = logging.getLogger(__name__)
router = Router()

# ═══════════════════════════════════════
# VILOYATLAR RO'YXATI
# ═══════════════════════════════════════
UZB_REGIONS = [
    "Toshkent", "Samarqand", "Buxoro",
    "Andijon", "Farg'ona", "Namangan",
    "Qashqadaryo", "Surxondaryo", "Sirdaryo",
    "Jizzax", "Navoiy", "Xorazm",
    "Qoraqalpog'iston",
]

# Timezone mapping for known countries
TIMEZONE_MAP = {
    "O'zbekiston": "Asia/Tashkent",
    "Узбекистан": "Asia/Tashkent",
    "Uzbekistan": "Asia/Tashkent",
    "Rossiya": "Europe/Moscow",
    "Россия": "Europe/Moscow",
    "Russia": "Europe/Moscow",
}


# ═══════════════════════════════════════
# YOSH TANLASH CALLBACK (Stage 0)
# ═══════════════════════════════════════
def build_age_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Yosh toifalarini tanlash uchun inline keyboard."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="18–24", callback_data="seg_age:18-24"),
            InlineKeyboardButton(text="25–34", callback_data="seg_age:25-34"),
            InlineKeyboardButton(text="35–44", callback_data="seg_age:35-44"),
        ],
        [
            InlineKeyboardButton(text="45–54", callback_data="seg_age:45-54"),
            InlineKeyboardButton(text="55+", callback_data="seg_age:55+"),
        ]
    ])


@router.callback_query(lambda c: c.data and c.data.startswith("seg_age:"))
async def process_age_selection(callback_query: CallbackQuery):
    """Yosh toifasi tanlandi."""
    user_id = callback_query.from_user.id
    age_group = callback_query.data.split(":")[1]

    await update_segment_data(user_id, {"age_group": age_group})

    user = await get_user(user_id)
    lang = user.get("language", "uz")

    await callback_query.message.edit_text(
        f"✅ {age_group} — " + t(lang, "seg_age_saved")
    )
    await callback_query.answer()


# ═══════════════════════════════════════
# DAVLAT TANLASH CALLBACK (Stage 1)
# ═══════════════════════════════════════
def build_country_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Davlat tanlash uchun inline keyboard."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🇺🇿 " + t(lang, "seg_uzb"), callback_data="seg_country:uzb"),
            InlineKeyboardButton(text="🇷🇺 " + t(lang, "seg_russia"), callback_data="seg_country:russia"),
        ],
        [
            InlineKeyboardButton(text="🌍 " + t(lang, "seg_other"), callback_data="seg_country:other"),
        ]
    ])


@router.callback_query(lambda c: c.data and c.data.startswith("seg_country:"))
async def process_country_selection(callback_query: CallbackQuery, state: FSMContext):
    """Davlat tanlandi."""
    user_id = callback_query.from_user.id
    choice = callback_query.data.split(":")[1]
    user = await get_user(user_id)
    lang = user.get("language", "uz")

    if choice == "uzb":
        # O'zbekiston — viloyat so'rash
        await callback_query.message.edit_text(t(lang, "seg_ask_region"))

        # Viloyatlarni 3 ta ustunli keyboard qilib chiqarish
        buttons = []
        row = []
        for i, region in enumerate(UZB_REGIONS):
            row.append(InlineKeyboardButton(text=region, callback_data=f"seg_region:{region}"))
            if len(row) == 3:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)

        kb = InlineKeyboardMarkup(inline_keyboard=buttons)
        await callback_query.message.answer(
            t(lang, "seg_ask_region"),
            reply_markup=kb
        )
        await callback_query.answer()

    elif choice == "russia":
        # Rossiya — timezone Europe/Moscow, viloyat so'ralmaydi
        await update_segment_data(user_id, {
            "country": "Rossiya",
            "timezone": "Europe/Moscow",
        })
        await complete_segmentation(user_id)

        await callback_query.message.edit_text(
            t(lang, "seg_location_saved", country=t(lang, "seg_russia"), timezone="Europe/Moscow")
        )
        await callback_query.answer()

    elif choice == "other":
        # Boshqa davlat — matn kiritish so'rash
        await callback_query.message.edit_text(t(lang, "seg_ask_country_name"))
        await state.set_state(SegmentationStates.waiting_for_country_name)
        await callback_query.answer()


# ═══════════════════════════════════════
# VILOYAT TANLASH CALLBACK (O'zbekiston)
# ═══════════════════════════════════════
@router.callback_query(lambda c: c.data and c.data.startswith("seg_region:"))
async def process_region_selection(callback_query: CallbackQuery):
    """Viloyat tanlandi (O'zbekiston)."""
    user_id = callback_query.from_user.id
    region = callback_query.data.split(":")[1]
    user = await get_user(user_id)
    lang = user.get("language", "uz")

    await update_segment_data(user_id, {
        "country": "O'zbekiston",
        "region": region,
        "timezone": "Asia/Tashkent",
    })
    await complete_segmentation(user_id)

    await callback_query.message.edit_text(
        t(lang, "seg_location_saved", country="O'zbekiston", timezone="Asia/Tashkent")
    )
    await callback_query.answer()


# ═══════════════════════════════════════
# BOSHQA DAVLAT — MATN KIRITISH (FSM)
# ═══════════════════════════════════════
@router.message(SegmentationStates.waiting_for_country_name, F.text)
async def process_country_name_text(message: Message, state: FSMContext):
    """Foydalanuvchi davlat nomini matn kiritdi."""
    user_id = message.from_user.id
    country_name = message.text.strip()
    user = await get_user(user_id)
    lang = user.get("language", "uz")

    # Groq AI orqali timezone aniqlash
    timezone = await _detect_timezone_with_ai(country_name, lang)

    await update_segment_data(user_id, {
        "country": country_name,
        "timezone": timezone,
    })
    await complete_segmentation(user_id)
    await state.clear()

    await message.answer(
        t(lang, "seg_location_saved", country=country_name, timezone=timezone)
    )


async def _detect_timezone_with_ai(country_name: str, lang: str) -> str:
    """Groq AI orqali davlat nomidan timezone aniqlash."""
    # Avval ma'lum davlatlarni tekshiramiz
    known = TIMEZONE_MAP.get(country_name)
    if known:
        return known

    try:
        from src.services.groq_service import groq_service
        ks = groq_service.get_best_key()
        response = await ks.client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {
                    "role": "system",
                    "content": "You are a timezone detector. Given a country name, return ONLY the IANA timezone string (e.g. 'Europe/London', 'Asia/Tokyo'). Return ONLY the timezone, nothing else. If unsure, return 'Asia/Tashkent'."
                },
                {
                    "role": "user",
                    "content": f"Country: {country_name}"
                }
            ],
            temperature=0,
            max_tokens=30,
        )
        tz = response.choices[0].message.content.strip()
        # Validate it looks like a timezone
        if "/" in tz and len(tz) < 40:
            return tz
        return "Asia/Tashkent"
    except Exception as e:
        logger.error(f"Failed to detect timezone for '{country_name}': {e}")
        return "Asia/Tashkent"


# ═══════════════════════════════════════
# QIZIQISHLAR SAVOLI CALLBACK
# ═══════════════════════════════════════
@router.callback_query(lambda c: c.data and c.data.startswith("seg_interest:"))
async def process_interest_answer(callback_query: CallbackQuery):
    """Qiziqish savoliga javob (Ha/Yo'q)."""
    user_id = callback_query.from_user.id
    # Format: seg_interest:yes:sport  or  seg_interest:no:sport
    parts = callback_query.data.split(":")
    answer = parts[1]         # "yes" or "no"
    category = parts[2]       # category name (short)

    user = await get_user(user_id)
    lang = user.get("language", "uz")

    if answer == "yes":
        await add_user_interest(user_id, category)
        await callback_query.message.edit_text(
            f"✅ {category} — " + t(lang, "seg_interest_added")
        )
    else:
        await callback_query.message.edit_text(
            t(lang, "seg_interest_skipped")
        )

    # Bu kategoriya uchun savol berilganini belgilaymiz
    await add_interest_query(user_id, category)
    await callback_query.answer()


# ═══════════════════════════════════════
# QIZIQISH SAVOLI YUBORISH FUNKSIYASI
# ═══════════════════════════════════════
def build_interest_keyboard(category_clean: str, lang: str) -> InlineKeyboardMarkup:
    """Qiziqish uchun Ha/Yo'q tugmalari."""
    # Callback data max 64 bytes, shuning uchun category ni qisqartiramiz
    cat_short = category_clean[:20]
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="✅ " + t(lang, "seg_yes"),
                callback_data=f"seg_interest:yes:{cat_short}"
            ),
            InlineKeyboardButton(
                text="❌ " + t(lang, "seg_no"),
                callback_data=f"seg_interest:no:{cat_short}"
            ),
        ]
    ])
