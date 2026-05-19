"""
Voice handler.
- Registration holatida registration_handler'ga qaytaradi
- Aks holda: Groq Whisper orqali transkripsiya, so'ng tranzaksiya pipeline'ga yuboradi

Error handling:
- Download xatosi         → err_voice_download
- Juda qisqa (< 1s)       → voice_too_short
- Juda uzun (> 120s)      → voice_too_long
- Noto'g'ri format        → voice_bad_format
- Barcha keylar tugagan   → err_ai_busy
- Boshqa transkripsiya    → err_voice_whisper
"""

import os
import asyncio
import logging
from aiogram import Router, F, Bot
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from src.services.groq_transcribe_service import (
    groq_transcribe_service,
    GroqAllKeysExhaustedError,
    GroqInvalidAudioError,
    GroqTranscribeError,
)
from src.handlers.message_handler import handle_transaction_text
from src.states import RegistrationStates
from src.database import get_user
from src.services.i18n import t
from src.services.error_handler import log_error, ErrorType

MAX_FILE_SIZE = 25 * 1024 * 1024  # 25 MB

logger = logging.getLogger(__name__)
router = Router()


@router.message(F.voice)
async def process_voice_message(message: Message, bot: Bot, state: FSMContext):
    current_state = await state.get_state()
    if current_state in [
        RegistrationStates.waiting_for_name.state,
        RegistrationStates.waiting_for_contact.state,
    ]:
        return

    user_id = message.from_user.id
    user = await get_user(user_id)
    lang = user.get("language", "uz")

    status_msg = await message.answer("⏳")

    duration = message.voice.duration or 0
    file_size = message.voice.file_size or 0
    file_id = message.voice.file_id
    logger.info(f"Voice: user={user_id}, duration={duration}s, size={file_size}b")

    if duration < 1:
        log_error(ErrorType.VOICE_TOO_SHORT, f"Voice too short: {duration}s", user_id)
        await status_msg.edit_text(t(lang, "voice_too_short"))
        return

    if duration > 120:
        log_error(ErrorType.VOICE_TOO_SHORT, f"Voice too long: {duration}s", user_id)
        await status_msg.edit_text(t(lang, "voice_too_long"))
        return

    if file_size and file_size > MAX_FILE_SIZE:
        log_error(ErrorType.VOICE_WHISPER_FAIL, f"Voice too large: {file_size}b", user_id)
        await status_msg.edit_text(t(lang, "voice_too_large"))
        return

    os.makedirs("temp", exist_ok=True)
    local_path = f"temp/{file_id}.ogg"

    try:
        file = await bot.get_file(file_id)
        await bot.download_file(file.file_path, local_path)
    except Exception as e:
        log_error(ErrorType.VOICE_DOWNLOAD, "Failed to download voice file", user_id, e)
        await status_msg.edit_text(t(lang, "err_voice_download"))
        return

    if not os.path.exists(local_path) or os.path.getsize(local_path) == 0:
        log_error(ErrorType.VOICE_DOWNLOAD, f"Downloaded file missing or empty: {local_path}", user_id)
        await status_msg.edit_text(t(lang, "err_voice_download"))
        return

    async def _send_typing():
        try:
            await bot.send_chat_action(chat_id=message.chat.id, action="typing")
        except Exception:
            pass
    asyncio.create_task(_send_typing())

    try:
        try:
            transcribed_text = await groq_transcribe_service.transcribe(local_path)
        except GroqAllKeysExhaustedError as e:
            log_error(ErrorType.VOICE_WHISPER_FAIL, "All Groq keys exhausted", user_id, e)
            await status_msg.edit_text(t(lang, "err_ai_busy"))
            return
        except GroqInvalidAudioError as e:
            log_error(ErrorType.VOICE_WHISPER_FAIL, "Groq rejected audio", user_id, e)
            await status_msg.edit_text(t(lang, "voice_bad_format"))
            return
        except GroqTranscribeError as e:
            log_error(ErrorType.VOICE_WHISPER_FAIL, "Groq transcription error", user_id, e)
            await status_msg.edit_text(t(lang, "err_voice_whisper"))
            return

        if not transcribed_text or len(transcribed_text.strip()) < 2:
            log_error(ErrorType.VOICE_WHISPER_FAIL, "Empty transcription result", user_id)
            await status_msg.edit_text(t(lang, "err_voice_whisper"))
            return

        if message.caption:
            transcribed_text = f"{transcribed_text}. Qo'shimcha izoh: {message.caption}"

        async def _delete_status():
            try:
                await status_msg.delete()
            except Exception:
                pass
        asyncio.create_task(_delete_status())

        await handle_transaction_text(message, transcribed_text, state)

    except Exception as e:
        log_error(ErrorType.UNKNOWN, "Voice post-transcription error", user_id, e)
        try:
            await status_msg.edit_text(t(lang, "err_voice_whisper"))
        except Exception:
            try:
                await message.answer(t(lang, "err_voice_whisper"))
            except Exception:
                pass
    finally:
        async def _cleanup():
            try:
                if os.path.exists(local_path):
                    os.remove(local_path)
            except Exception:
                pass
        asyncio.create_task(_cleanup())
