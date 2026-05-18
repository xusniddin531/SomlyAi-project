"""
Voice handler.
Routes voice messages:
- If in registration (waiting_for_name) → handled by registration_handler
- If in registration (waiting_for_contact) → handled by registration_handler
- Otherwise → transcribe (via Gemini's Whisper model) and pass to transaction pipeline

MUHIM: Transkripsiya OpenAI Whisper API orqali emas, Gemini orqali bajariladi.
Gemini o'z serverlarida `whisper-large-v3-turbo` va `whisper-large-v3` modellarini host qiladi.

Error handling:
- Voice file download failure → err_voice_download
- Voice too short (< 1s) → err_voice_too_short
- Voice too long (> 120s) or too large (> 25MB) → specific error
- Invalid audio (bad format) → err_voice_whisper
- All Gemini keys exhausted (401/quota) → err_ai_down
- Rate-limited → err_ai_busy
- Gemini server error → err_ai_down
"""

import os
import logging
from aiogram import Router, F, Bot
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from src.services.gemini_service import (
    gemini_service, GeminiServerError,
    WhisperInvalidAudioError, WhisperAllKeysExhaustedError,
)
from src.handlers.message_handler import handle_transaction_text
from src.states import RegistrationStates
from src.database import get_user
from src.services.i18n import t
from src.services.error_handler import log_error, ErrorType

GEMINI_AUDIO_MAX_FILE_SIZE = 25 * 1024 * 1024  # Gemini audio endpoint limit: 25MB
WHISPER_MAX_FILE_SIZE = GEMINI_AUDIO_MAX_FILE_SIZE  # backward-compat alias

logger = logging.getLogger(__name__)
router = Router()


@router.message(F.voice)
async def process_voice_message(message: Message, bot: Bot, state: FSMContext):
    # ═══════════════════════════════════════
    # Registration state tekshiruvi
    # ═══════════════════════════════════════
    current_state = await state.get_state()
    if current_state in [
        RegistrationStates.waiting_for_name.state,
        RegistrationStates.waiting_for_contact.state,
    ]:
        return

    user_id = message.from_user.id

    # Get user language for error messages
    user = await get_user(user_id)
    lang = user.get("language", "uz")

    status_msg = await message.answer(t(lang, "voice_processing"))

    # ── Check voice duration ──
    duration = message.voice.duration or 0
    file_size = message.voice.file_size or 0
    file_id = message.voice.file_id
    logger.info(f"Voice received: user={user_id}, file_id={file_id}, duration={duration}s, size={file_size}b")

    if duration < 1:  # Less than 1 second (~0.5s rounded)
        log_error(ErrorType.VOICE_TOO_SHORT, f"Voice too short: {duration}s", user_id)
        await status_msg.edit_text(t(lang, "voice_too_short"))
        return

    if duration > 120:
        log_error(ErrorType.VOICE_TOO_SHORT, f"Voice too long: {duration}s", user_id)
        await status_msg.edit_text(t(lang, "voice_too_long"))
        return

    if file_size and file_size > WHISPER_MAX_FILE_SIZE:
        log_error(ErrorType.VOICE_WHISPER_FAIL, f"Voice file too large: {file_size}b", user_id)
        await status_msg.edit_text(t(lang, "voice_too_large"))
        return

    # ── Download voice file ──
    os.makedirs("temp", exist_ok=True)
    local_path = f"temp/{file_id}.ogg"

    try:
        file = await bot.get_file(file_id)
        file_path = file.file_path
        await bot.download_file(file_path, local_path)
    except Exception as e:
        log_error(ErrorType.VOICE_DOWNLOAD, f"Failed to download voice file", user_id, e)
        await status_msg.edit_text(t(lang, "err_voice_download"))
        return

    # ── Verify file actually downloaded ──
    if not os.path.exists(local_path) or os.path.getsize(local_path) == 0:
        log_error(ErrorType.VOICE_DOWNLOAD, f"Downloaded file missing or empty: {local_path}", user_id)
        await status_msg.edit_text(t(lang, "err_voice_download"))
        return

    # ── Typing indicator fire-and-forget (foydalanuvchi darrov his qiladi) ──
    import asyncio as _asyncio
    async def _send_typing():
        try:
            await bot.send_chat_action(chat_id=message.chat.id, action="typing")
        except Exception:
            pass
    _asyncio.create_task(_send_typing())

    try:
        # ── Gemini Whisper transcription (Gemini SDK orqali, OpenAI emas) ──
        # NOTE: parallel context fetch transcribe BILAN BIRGA bo'lishi mumkin, lekin
        # transcribe natijasi (matn) AI prompt'ga kerak — context fetch transcribe
        # tugashidan oldin handle_transaction_text ichida boshlanadi (asyncio.gather).
        try:
            transcribed_text = await gemini_service.transcribe_audio_with_retry(local_path)
        except WhisperAllKeysExhaustedError as e:
            log_error(ErrorType.VOICE_WHISPER_FAIL, f"All Gemini keys exhausted for audio", user_id, e)
            await status_msg.edit_text(t(lang, "err_ai_down"))
            return
        except WhisperInvalidAudioError as e:
            log_error(ErrorType.VOICE_WHISPER_FAIL, f"Invalid audio rejected by Gemini Whisper", user_id, e)
            await status_msg.edit_text(t(lang, "voice_bad_format"))
            return
        except GeminiServerError:
            await status_msg.edit_text(t(lang, "err_ai_busy"))
            return
        except GeminiServerError:
            await status_msg.edit_text(t(lang, "err_ai_down"))
            return
        except Exception as e:
            log_error(ErrorType.VOICE_WHISPER_FAIL, f"Gemini Whisper unexpected failure", user_id, e)
            await status_msg.edit_text(t(lang, "err_voice_whisper"))
            return

        # ── Check if transcription is empty/too short ──
        if not transcribed_text or len(transcribed_text.strip()) < 2:
            log_error(ErrorType.VOICE_WHISPER_FAIL, f"Empty transcription result (size={os.path.getsize(local_path)}b)", user_id)
            await status_msg.edit_text(t(lang, "err_voice_whisper"))
            return

        # ── Merge with Caption ──
        if message.caption:
            transcribed_text = f"{transcribed_text}. Qo'shimcha izoh: {message.caption}"

        # ── Status xabarni fire-and-forget o'chiramiz (foydalanuvchini kutkazmaslik uchun) ──
        async def _delete_status():
            try:
                await status_msg.delete()
            except Exception:
                pass
        import asyncio as _asyncio
        _asyncio.create_task(_delete_status())

        # Tranzaksiya pipeline'ga DARROV yuboramiz (status o'chishini kutmaymiz)
        await handle_transaction_text(message, transcribed_text, state)

    except Exception as e:
        # This catches errors from handle_transaction_text or status_msg ops
        log_error(ErrorType.UNKNOWN, f"Voice post-transcription error", user_id, e)
        try:
            await status_msg.edit_text(t(lang, "err_voice_whisper"))
        except Exception:
            try:
                await message.answer(t(lang, "err_voice_whisper"))
            except Exception:
                pass
    finally:
        # Faylni asinxron o'chiramiz (foydalanuvchi javobini kutmaymiz)
        async def _cleanup_file():
            try:
                if os.path.exists(local_path):
                    os.remove(local_path)
            except Exception:
                pass
        import asyncio as _asyncio
        _asyncio.create_task(_cleanup_file())
