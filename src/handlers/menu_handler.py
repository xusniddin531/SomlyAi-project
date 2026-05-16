from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, WebAppInfo
from src.database import get_webapp_url, get_user
from src.services.i18n import t

router = Router()

async def get_main_keyboard(lang: str = "uz"):
    from aiogram.types import ReplyKeyboardRemove
    return ReplyKeyboardRemove()

def get_add_buttons():
    return [t("uz", "main_menu_add"), t("ru", "main_menu_add"), t("en", "main_menu_add")]

def get_account_buttons():
    return [t("uz", "main_menu_account"), t("ru", "main_menu_account"), t("en", "main_menu_account")]

@router.message(F.text.in_(get_add_buttons()))
async def process_add_button(message: Message):
    user = await get_user(message.from_user.id)
    lang = user.get("language", "uz")
    text = t(lang, "add_prompt")
    # Re-send the keyboard just in case they lost it
    kbd = await get_main_keyboard(lang)
    await message.answer(text, reply_markup=kbd)

@router.message(F.text.in_(get_account_buttons()))
async def process_my_account_button(message: Message):
    user = await get_user(message.from_user.id)
    lang = user.get("language", "uz")
    url = await get_webapp_url()
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kbd = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(lang, "open_btn"), web_app=WebAppInfo(url=url))]
    ])
    await message.answer(t(lang, "open_miniapp_prompt"), reply_markup=kbd)
