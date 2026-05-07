import logging
import threading
import tempfile
import os
from typing import Optional
from backend.config import settings

logger = logging.getLogger(__name__)

_tts_lock = threading.Lock()


def _get_engine():
    """Create a new pyttsx3 engine instance (not thread-safe to share)."""
    try:
        import pyttsx3
        engine = pyttsx3.init()
        engine.setProperty("rate", settings.tts_rate)
        engine.setProperty("volume", settings.tts_volume)
        voices = engine.getProperty("voices")
        if voices and len(voices) > settings.tts_voice_index:
            engine.setProperty("voice", voices[settings.tts_voice_index].id)
        return engine
    except Exception as exc:
        logger.error("pyttsx3 init failed: %s", exc)
        return None


def speak_text(text: str) -> bool:
    """Speak text aloud via system TTS. Blocking call."""
    with _tts_lock:
        engine = _get_engine()
        if engine is None:
            logger.warning("TTS unavailable — text: %s", text[:80])
            return False
        try:
            engine.say(text)
            engine.runAndWait()
            return True
        except Exception as exc:
            logger.error("TTS speak failed: %s", exc)
            return False


def text_to_wav(text: str, output_path: Optional[str] = None) -> Optional[str]:
    """
    Convert text to a WAV file.
    Returns path to generated file, or None on failure.
    """
    if output_path is None:
        fd, output_path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)

    with _tts_lock:
        engine = _get_engine()
        if engine is None:
            return None
        try:
            engine.save_to_file(text, output_path)
            engine.runAndWait()
            return output_path
        except Exception as exc:
            logger.error("TTS save_to_file failed: %s", exc)
            return None
