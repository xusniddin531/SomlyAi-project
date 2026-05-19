"""
Groq Whisper transcription service.
- Model: whisper-large-v3
- Key rotation: GROQ_API_KEYS (vergul bilan ajratilgan, max 5 ta)
- Rate limit: keyingi keyga o'tadi; barchasi tugasa 30s kutib qayta urinadi
"""

import os
import asyncio
import logging
import itertools
from groq import Groq, RateLimitError, BadRequestError

from src.config import GROQ_API_KEYS

logger = logging.getLogger(__name__)
WHISPER_MODEL = "whisper-large-v3"


class GroqTranscribeError(Exception):
    """Umumiy Groq transkripsiya xatosi."""

class GroqInvalidAudioError(GroqTranscribeError):
    """Audio fayl noto'g'ri yoki qabul qilinmadi."""

class GroqAllKeysExhaustedError(GroqTranscribeError):
    """Barcha Groq API kalitlari rate-limit'ga uchradi."""


class GroqTranscribeService:
    def __init__(self):
        self._clients = []
        if not GROQ_API_KEYS:
            logger.error("GROQ_API_KEYS .env faylida topilmadi!")
        else:
            self._clients = [Groq(api_key=k) for k in GROQ_API_KEYS if k]
            logger.info(f"GroqTranscribeService: {len(self._clients)} ta kalit yuklandi")

        self._cycle = itertools.cycle(self._clients) if self._clients else None
        self._n = len(self._clients)

    def _next(self) -> Groq:
        return next(self._cycle)

    async def transcribe(self, file_path: str) -> str:
        if not os.path.exists(file_path):
            raise GroqInvalidAudioError(f"Audio fayl topilmadi: {file_path}")
        if os.path.getsize(file_path) == 0:
            raise GroqInvalidAudioError(f"Audio fayl bo'sh: {file_path}")
        if not self._clients:
            raise GroqTranscribeError("Groq API kalitlari sozlanmagan")

        last_err = None

        for attempt in range(2):
            if attempt:
                logger.warning("Barcha Groq kalitlari rate-limit. 30 soniya kutilmoqda...")
                await asyncio.sleep(30)

            for _ in range(self._n):
                client = self._next()
                try:
                    with open(file_path, "rb") as f:
                        result = await asyncio.to_thread(
                            client.audio.transcriptions.create,
                            model=WHISPER_MODEL,
                            file=(os.path.basename(file_path), f, "audio/ogg"),
                            response_format="text",
                        )
                    text = result if isinstance(result, str) else getattr(result, "text", str(result))
                    return text.strip()
                except RateLimitError as e:
                    logger.warning(f"Groq kalit rate-limit, keyingisiga o'tilmoqda: {e}")
                    last_err = e
                except BadRequestError as e:
                    raise GroqInvalidAudioError(f"Groq audio qabul qilmadi: {e}")
                except Exception as e:
                    raise GroqTranscribeError(f"Groq xatosi: {e}")

        raise GroqAllKeysExhaustedError(f"Barcha Groq kalitlari tugadi. Oxirgi xato: {last_err}")


groq_transcribe_service = GroqTranscribeService()
