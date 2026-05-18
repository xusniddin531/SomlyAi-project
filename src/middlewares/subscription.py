"""
Mandatory Channel Subscription Middleware.
Intercepts all messages/callbacks and checks subscription every 24 hours.
After subscription is verified, redirects to registration if not complete.

24-SOATLIK TEKSHIRUV QOIDASI:
- last_channel_check dan 24 soat o'tmagan → tekshirmaydi, o'tkazib yuboradi
- 24 soat o'tgan yoki hech tekshirilmagan → Telegram API orqali tekshiradi
- Obuna bo'lsa → last_channel_check yangilanadi
- Obuna bo'lmasa → bloklash xabari chiqadi
- Bot kanalda admin emas → asosiy adminga alert yuboriladi
"""

import logging
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware, Bot
from aiogram.types import Message, CallbackQuery, TelegramObject, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from src.database import (
    get_all_channels, get_user,
    update_last_channel_check, should_check_channel_subscription,
)
from src.states import RegistrationStates
from src.services.i18n import t
from src.config import ADMIN_ID

logger = logging.getLogger(__name__)

# Kanalga bot admin qilinmagan haqida bir marta alert yuborish uchun cache
_admin_alert_sent = set()


class SubscriptionMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:

        bot: Bot = data.get("bot")

        # Get user info
        if isinstance(event, Message):
            user = event.from_user
        elif isinstance(event, CallbackQuery):
            user = event.from_user
        else:
            return await handler(event, data)

        if not user:
            return await handler(event, data)

        user_id = user.id

        # ════════════════════════════════════════════
        # ADMIN BYPASS (env ADMIN_ID + hardcoded super admin 6028715926)
        # ════════════════════════════════════════════
        from src.database import SUPER_ADMIN_ID
        try:
            uid_int = int(user_id)
        except (TypeError, ValueError):
            uid_int = 0
        if uid_int == SUPER_ADMIN_ID or str(user_id) == str(ADMIN_ID):
            return await handler(event, data)

        # ════════════════════════════════════════════
        # BYPASS — hech qachon tekshirmaslik kerak bo'lgan holatlar
        # ════════════════════════════════════════════
        if isinstance(event, Message):
            # /start, /language buyruqlari
            if event.text and (event.text.startswith("/start") or event.text.startswith("/language")):
                return await handler(event, data)
            # Contact (registration davomida)
            if event.contact:
                return await handler(event, data)
        elif isinstance(event, CallbackQuery):
            # Til tanlash callback'lari
            if event.data and event.data.startswith("lang_"):
                return await handler(event, data)
            # Onboarding kanal tekshirish callback
            if event.data and event.data == "check_sub_onboarding":
                return await handler(event, data)
            # "Obuna bo'ldim" tugmasi — bu yerda tekshirish kerak, bypass QILMAYMIZ

        # ════════════════════════════════════════════
        # FSM state tekshiruvi — agar registration davomida bo'lsa, o'tkazib yuborish
        # ════════════════════════════════════════════
        state: FSMContext = data.get("state")
        if state:
            current_state = await state.get_state()
            if current_state and current_state in [
                RegistrationStates.waiting_for_name.state,
                RegistrationStates.waiting_for_contact.state,
                # Legacy states ham
                RegistrationStates.waiting_for_age.state,
                RegistrationStates.waiting_for_location.state,
                RegistrationStates.waiting_for_region.state,
                RegistrationStates.waiting_for_country.state,
            ]:
                return await handler(event, data)

        # ════════════════════════════════════════════
        # USER TILINI OLISH
        # ════════════════════════════════════════════
        db_user = await get_user(user_id)
        lang = db_user.get("language", "uz") if db_user else "uz"

        # ════════════════════════════════════════════
        # AGAR REGISTRATION TUGAMAGAN BO'LSA
        # ════════════════════════════════════════════
        if db_user and not db_user.get("registration_complete"):
            return await self._redirect_to_registration(event, data, lang, state)

        # ════════════════════════════════════════════
        # "CHECK_SUB" CALLBACK — Foydalanuvchi "Obuna bo'ldim" tugmasini bosdi
        # ════════════════════════════════════════════
        if isinstance(event, CallbackQuery) and event.data == "check_sub":
            return await self._handle_check_sub_callback(event, bot, user_id, lang)

        # ════════════════════════════════════════════
        # 24 SOATLIK TEKSHIRUV — vaqti kelganmi?
        # ════════════════════════════════════════════
        if db_user and not should_check_channel_subscription(db_user):
            # 24 soat hali o'tmagan — tekshirmasdan o'tkazamiz
            return await handler(event, data)

        # ════════════════════════════════════════════
        # KANAL OBUNASI TEKSHIRUVI
        # ════════════════════════════════════════════
        channels = await get_all_channels()
        if not channels:
            # Kanallar yo'q bo'lsa — tekshirish shart emas
            if db_user:
                await update_last_channel_check(user_id)
            return await handler(event, data)

        not_subscribed = []
        for ch in channels:
            is_subscribed = await self._check_single_channel(bot, ch, user_id)
            if not is_subscribed:
                not_subscribed.append(ch)

        if not_subscribed:
            # Obuna bo'lmagan kanallar bor — bloklash
            return await self._show_subscription_required(event, not_subscribed, lang)

        # Barcha kanallarga obuna — vaqtni yangilash
        await update_last_channel_check(user_id)
        return await handler(event, data)

    async def _check_single_channel(self, bot: Bot, channel: dict, user_id: int) -> bool:
        """Bitta kanalni tekshirish. Bot admin bo'lmasa adminga alert yuboradi."""
        link = channel["link"]
        chat_identifier = link
        if "t.me/" in link and "+" not in link:
            username = link.split("t.me/")[1].split("/")[0]
            chat_identifier = f"@{username}"

        try:
            member = await bot.get_chat_member(chat_id=chat_identifier, user_id=user_id)
            if member.status in ["left", "kicked", "restricted"]:
                return False
            return True
        except Exception as e:
            error_str = str(e).lower()
            logger.warning(f"Sub check failed for {chat_identifier}: {e}")

            # ════════════════════════════════════════
            # BOT ADMIN EMAS — Adminga alert yuborish
            # ════════════════════════════════════════
            if "chat not found" in error_str or "not enough rights" in error_str or "bot is not a member" in error_str or "forbidden" in error_str or "inaccessible" in error_str:
                await self._send_admin_alert(bot, channel, chat_identifier)

            # Bot tekshira olmasa — userni BLOKLAMAYMIZ, o'tkazib yuboramiz
            # Aks holda botni ishlatib bo'lmay qoladi
            return True

    async def _send_admin_alert(self, bot: Bot, channel: dict, chat_identifier: str):
        """Asosiy adminga bot admin emasligini xabar berish (faqat bir marta)."""
        alert_key = f"{chat_identifier}"
        if alert_key in _admin_alert_sent:
            return  # Allaqachon xabar yuborilgan

        _admin_alert_sent.add(alert_key)
        try:
            await bot.send_message(
                chat_id=int(ADMIN_ID),
                text=(
                    f"⚠️ <b>Diqqat!</b>\n\n"
                    f"Bot <code>{chat_identifier}</code> kanalida <b>admin emas!</b>\n\n"
                    f"Obuna tekshiruvi ishlamaydi. Iltimos, botni shu kanalga admin qilib qo'ying.\n\n"
                    f"Kanal nomi: {channel.get('name', '-')}\n"
                    f"Kanal linki: {channel.get('link', '-')}"
                ),
                parse_mode="HTML"
            )
            logger.warning(f"Admin alert sent: bot is not admin in {chat_identifier}")
        except Exception as e:
            logger.error(f"Failed to send admin alert: {e}")

    async def _handle_check_sub_callback(self, callback: CallbackQuery, bot: Bot, user_id: int, lang: str):
        """'Obuna bo'ldim' tugmasi bosildi — qayta tekshirish."""
        channels = await get_all_channels()
        if not channels:
            await callback.message.delete()
            await update_last_channel_check(user_id)
            await callback.answer()
            return

        not_subscribed = []
        for ch in channels:
            is_subscribed = await self._check_single_channel(bot, ch, user_id)
            if not is_subscribed:
                not_subscribed.append(ch)

        if not_subscribed:
            # Hali obuna bo'lmagan
            await callback.answer(
                t(lang, "channel_not_subscribed"),
                show_alert=True
            )
            return

        # Obuna bo'lgan — muvaffaqiyatli!
        await callback.message.delete()
        await update_last_channel_check(user_id)

        from src.handlers.menu_handler import get_main_keyboard
        kbd = await get_main_keyboard(lang)
        await callback.message.answer(t(lang, "channel_subscribed"), reply_markup=kbd)
        await callback.answer()

    async def _show_subscription_required(self, event, not_subscribed, lang):
        """Obuna bo'lmagan kanallarga tugma chiqarish."""
        buttons = []
        for ch in not_subscribed:
            buttons.append([InlineKeyboardButton(text=f"📢 {ch['name']}", url=ch['link'])])

        buttons.append([InlineKeyboardButton(
            text="✅ " + t(lang, "channel_check_btn"),
            callback_data="check_sub"
        )])
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

        text = t(lang, "channel_resubscribe")

        if isinstance(event, Message):
            await event.answer(text, reply_markup=keyboard)
        elif isinstance(event, CallbackQuery):
            if event.data == "check_sub":
                await event.message.answer(text, reply_markup=keyboard)
                await event.answer(
                    t(lang, "channel_not_subscribed"),
                    show_alert=True
                )
            else:
                await event.answer("⚠️", show_alert=False)

    async def _redirect_to_registration(self, event, data, lang, state):
        """Ro'yxatdan o'tishga yo'naltirish."""
        if state:
            await state.set_state(RegistrationStates.waiting_for_name)

        text = t(lang, "ask_name")

        if isinstance(event, Message):
            await event.answer(text)
        elif isinstance(event, CallbackQuery):
            await event.message.answer(text)
            await event.answer()
