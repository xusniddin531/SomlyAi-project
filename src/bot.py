"""
Somly AI Bot — main entry point.

Wires together:
- start_handler       (/start, /help, /language + lang_ callbacks)
- registration_handler (FSM: name + contact collection)
- admin_handler       (/stats, /admin, /add_channel, /send)
- export_handler      (/excel)
- balance_handler     (/balance, /newbalance, /setlimit, /cancel + FSM)
- debt_handler        (/debts + callback queries + FSM)
- voice_handler       (voice messages → Whisper → text pipeline)
- message_handler     (text messages → AI → transaction pipeline) ← LAST (catch-all)
- scheduler           (daily/monthly reminders + dynamic one-time reminders)
- Global error handler for unhandled exceptions
"""

import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand, ErrorEvent
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest, TelegramRetryAfter, TelegramConflictError
from src.config import BOT_TOKEN
from src.handlers import (
    start_handler,
    registration_handler,
    segment_handler,
    limit_handler,
    menu_handler,
    photo_handler,
    voice_handler,
    message_handler,
    admin_handler,
    export_handler,
    group_handler,
)
from src.middlewares.antispam import AntiSpamMiddleware
from src.middlewares.subscription import SubscriptionMiddleware
from src.services.scheduler import setup_scheduler
from src.api import start_api_server
from src.services.error_handler import (
    log_error, handle_error, ErrorType, split_long_message
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

# Module-level shutdown signal — TelegramConflictError yoki SIGTERM tetiklashi mumkin
_CONFLICT_SHUTDOWN_EVENT: asyncio.Event = None


async def main():
    global _CONFLICT_SHUTDOWN_EVENT
    _CONFLICT_SHUTDOWN_EVENT = asyncio.Event()
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    # ── Global error handler ──
    @dp.errors()
    async def global_error_handler(event: ErrorEvent):
        """Catch all unhandled errors in handlers."""
        exception = event.exception
        update = event.update

        # Extract user_id from update if possible
        user_id = 0
        if update and update.message:
            user_id = update.message.from_user.id if update.message.from_user else 0
        elif update and update.callback_query:
            user_id = update.callback_query.from_user.id if update.callback_query.from_user else 0

        # ── User blocked the bot ──
        if isinstance(exception, TelegramForbiddenError):
            log_error(ErrorType.TELEGRAM_BLOCKED, f"User {user_id} blocked the bot", user_id, exception)
            if user_id:
                try:
                    from src.database import users_collection
                    await users_collection.update_one(
                        {"telegram_id": user_id},
                        {"$set": {"is_active": False}}
                    )
                except Exception:
                    pass
            return True  # Error handled

        # ── Message too long ──
        if isinstance(exception, TelegramBadRequest) and "message is too long" in str(exception).lower():
            log_error(ErrorType.TELEGRAM_MESSAGE_TOO_LONG, f"Message too long for {user_id}", user_id, exception)
            # Try to send truncated version
            if update and update.message:
                try:
                    await update.message.answer("⚠️ Xabar juda uzun. Qisqaroq formatda ko'rsatildi.")
                except Exception:
                    pass
            return True

        # ── Telegram Conflict (boshqa nusxa polling qilmoqda) ──
        # Bu sodir bo'lsa, joriy konteyner gracefully o'zini yopadi —
        # cheksiz "Conflict" loop'iga tushib qolmaslik uchun.
        if isinstance(exception, TelegramConflictError):
            logger.error(
                "🚨 TelegramConflictError: boshqa nusxa shu token bilan polling qilyapti. "
                "Joriy konteyner yopilmoqda (orkestrator restart qiladi)."
            )
            # Bot yopishni shu jarayonda qilish — main() ichida shutdown_event tetiklash
            try:
                _CONFLICT_SHUTDOWN_EVENT.set()
            except NameError:
                pass
            return True

        # ── Flood limit (429) ──
        if isinstance(exception, TelegramRetryAfter):
            log_error(ErrorType.TELEGRAM_GENERAL, f"Global rate limit. Wait {exception.retry_after}s", user_id, exception)
            # For specific safe_send_message we handle it there, but if it hits here:
            if update and update.message:
                try:
                    import asyncio
                    await asyncio.sleep(exception.retry_after)
                    await update.message.answer("⏳ Bot qayta tiklandi.")
                except Exception:
                    pass
            return True

        # ── MongoDB connection errors ──
        error_str = str(exception).lower()
        if "serverselectiontimeouterror" in error_str or "connection" in error_str and "mongo" in error_str:
            log_error(ErrorType.MONGODB_CONNECTION, f"MongoDB connection error", user_id, exception)
            await handle_error(bot, ErrorType.MONGODB_CONNECTION, str(exception), user_id, exception)
            if update and update.message:
                try:
                    from src.services.i18n import t
                    from src.database import get_user
                    user = await get_user(user_id) if user_id else {}
                    lang = user.get("language", "uz") if user else "uz"
                    await update.message.answer(t(lang, "err_db_connection"))
                except Exception:
                    try:
                        await update.message.answer("⚠️ Texnik muammo. Jamoamiz xabardor qilindi.")
                    except Exception:
                        pass
            return True

        # ── All other unhandled errors ──
        log_error(ErrorType.UNKNOWN, f"Unhandled error: {type(exception).__name__}: {str(exception)}", user_id, exception)
        logger.exception(f"Unhandled error in bot:", exc_info=exception)

        # Try to notify user
        if update and update.message and user_id:
            try:
                from src.services.i18n import t
                from src.database import get_user
                user = await get_user(user_id) if user_id else {}
                lang = user.get("language", "uz") if user else "uz"
                await update.message.answer(t(lang, "err_general"))
            except Exception:
                pass

        # Alert admin for unknown errors
        try:
            await handle_error(bot, ErrorType.UNKNOWN, f"{type(exception).__name__}: {str(exception)[:500]}", user_id, exception)
        except Exception:
            pass

        return True

    # ── Register middleware ──
    dp.message.middleware(AntiSpamMiddleware())
    dp.callback_query.middleware(AntiSpamMiddleware())
    dp.message.middleware(SubscriptionMiddleware())
    dp.callback_query.middleware(SubscriptionMiddleware())

    # ── Register routers ──
    # Order matters! Command routers first, then FSM routers,
    # then voice, then text (catch-all) last.
    dp.include_router(admin_handler.router)         # /stats, /admin, /add_channel, /send
    dp.include_router(start_handler.router)         # /start, /help, /language + lang_ callbacks
    dp.include_router(registration_handler.router)  # FSM: name + contact
    dp.include_router(segment_handler.router)       # Segmentation questions + interests
    dp.include_router(export_handler.router)        # /excel
    dp.include_router(limit_handler.router)         # /setlimit
    dp.include_router(menu_handler.router)          # main reply keyboard menus
    dp.include_router(group_handler.router)          # group messages (before catch-all)
    dp.include_router(photo_handler.router)           # photo messages (QR scan)
    dp.include_router(voice_handler.router)         # voice messages
    dp.include_router(message_handler.router)       # text messages (catch-all — MUST be last)

    # ── Start scheduler ──
    setup_scheduler(bot)

    # ── Start API Server ──
    await start_api_server(bot)

    # ── Validate Gemini API keys ──
    from src.services.gemini_service import gemini_service
    await gemini_service.validate_keys_on_startup()

    # ── Ensure MongoDB indexes (10-100x faster queries) ──
    from src.database import ensure_indexes
    await ensure_indexes()

    # ── Graceful shutdown handler ──
    # Docker SIGTERM yuborganda 30s ichida toza yopilish kerak.
    # Aks holda Docker SIGKILL yuboradi va joriy task'lar yo'qoladi.
    # shutdown_event = global _CONFLICT_SHUTDOWN_EVENT (SIGTERM + Conflict ikkalasi tetiklashi mumkin)
    shutdown_event = _CONFLICT_SHUTDOWN_EVENT

    def _handle_signal(sig_name: str):
        logger.warning(f"⚠️ {sig_name} signali qabul qilindi. Graceful shutdown boshlanmoqda...")
        shutdown_event.set()

    # POSIX signallar (Linux/Docker)
    try:
        import signal as _signal
        loop = asyncio.get_running_loop()
        for sig in (_signal.SIGTERM, _signal.SIGINT):
            try:
                loop.add_signal_handler(sig, _handle_signal, sig.name)
            except (NotImplementedError, RuntimeError):
                # Windows'da add_signal_handler ishlamaydi — KeyboardInterrupt orqali boshqariladi
                pass
    except Exception as e:
        logger.warning(f"Signal handler setup failed: {e}")

    # ── Start polling ──
    logger.info("🚀 Somly AI Bot ishga tushdi!")
    await bot.set_my_commands([
        BotCommand(command="language", description="Tilni o'zgartirish"),
        BotCommand(command="setlimit", description="Oylik limit o'rnatish"),
        BotCommand(command="excel", description="Hisobotni yuklab olish"),
    ])
    await bot.delete_webhook(drop_pending_updates=True)

    # Polling'ni background task sifatida ishga tushiramiz — SIGTERM kelganda to'xtatish uchun
    polling_task = asyncio.create_task(dp.start_polling(bot, handle_signals=False))
    shutdown_task = asyncio.create_task(shutdown_event.wait())

    done, pending = await asyncio.wait(
        {polling_task, shutdown_task},
        return_when=asyncio.FIRST_COMPLETED,
    )

    # SIGTERM kelgan bo'lsa — graceful shutdown
    if shutdown_event.is_set():
        logger.info("Polling'ni to'xtatmoqdamiz...")
        try:
            await dp.stop_polling()
        except Exception as e:
            logger.warning(f"stop_polling error: {e}")

        # Joriy task'larga 5 soniya beramiz tugashga
        try:
            await asyncio.wait_for(polling_task, timeout=5.0)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            polling_task.cancel()

        # WebSocket connections'ni xabardor qilamiz
        try:
            from src.ws_manager import ws_manager
            await ws_manager.broadcast_all("server_restarting")
        except Exception:
            pass

        # Bot session'ni yopish (telegram connection)
        try:
            await bot.session.close()
        except Exception:
            pass

        logger.info("✅ Bot toza yopildi.")
    else:
        # Polling o'zi tugagan (xato) — keyingi pending task'ni tozalaymiz
        for task in pending:
            task.cancel()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt — yopilmoqda...")
