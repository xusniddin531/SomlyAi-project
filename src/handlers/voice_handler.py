"""
Voice handler.
Routes voice messages:
- If in registration (waiting_for_name) → handled by registration_handler
- If in registration (waiting_for_contact) → handled by registration_handler
- Otherwise → transcribe and pass to transaction pipeline

Error handling:
- Voice file download failure → err_voice_download
- Voice too short (< 0.5s) → err_voice_too_short
- Whisper transcription failure → err_voice_whisper
- All Groq keys exhausted → err_ai_busy
- Groq server error → err_ai_down
"""

import os
import logging
from aiogram import Router, F, Bot
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from src.services.groq_service import groq_service, GroqQueueError, GroqServerError
from src.handlers.message_handler import handle_transaction_text
from src.states import RegistrationStates
from src.database import get_user
from src.services.i18n import t
from src.services.error_handler import log_error, ErrorType

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
    if duration < 1:  # Less than 1 second (~0.5s rounded)
        log_error(ErrorType.VOICE_TOO_SHORT, f"Voice too short: {duration}s", user_id)
        await status_msg.edit_text("🎤 Ovoz juda qisqa, qaytadan yuboring")
        return
        
    if duration > 120:
        log_error(ErrorType.VOICE_TOO_SHORT, f"Voice too long: {duration}s", user_id)
        await status_msg.edit_text("🎤 Ovoz juda uzun.\nIltimos qisqaroq yuboring")
        return

    # ── Download voice file ──
    file_id = message.voice.file_id
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

    try:
        # ── Whisper transcription ──
        try:
            transcribed_text = await groq_service.transcribe_audio_with_retry(local_path)
        except GroqQueueError:
            await status_msg.edit_text(t(lang, "err_ai_busy"))
            return
        except GroqServerError:
            await status_msg.edit_text(t(lang, "err_ai_down"))
            return
        except Exception as e:
            log_error(ErrorType.VOICE_WHISPER_FAIL, f"Whisper failed", user_id, e)
            await status_msg.edit_text(t(lang, "err_voice_whisper"))
            return

        # ── Check if transcription is empty/too short ──
        if not transcribed_text or len(transcribed_text.strip()) < 2:
            log_error(ErrorType.VOICE_WHISPER_FAIL, f"Empty transcription result", user_id)
            await status_msg.edit_text(t(lang, "err_voice_whisper"))
            return
            
        # ── Merge with Caption ──
        if message.caption:
            transcribed_text = f"{transcribed_text}. Qo'shimcha izoh: {message.caption}"

        # ── Delete status message and process ──
        await status_msg.delete()

        # Tranzaksiya pipeline'ga yuborish
        await handle_transaction_text(message, transcribed_text, state)

    except Exception as e:
        log_error(ErrorType.UNKNOWN, f"Voice processing error", user_id, e)
        try:
            await status_msg.edit_text(t(lang, "err_general"))
        except Exception:
            pass
    finally:
        if os.path.exists(local_path):
            os.remove(local_path)
