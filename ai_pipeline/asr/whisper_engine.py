
import io   
import logging
import time
import tempfile
import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Generator, List
import numpy as np

logger = logging.getLogger(__name__)

# Lazy import — Whisper is heavy; only load when needed
_whisper_model = None


def get_whisper_model():
    """Load and cache the Faster Whisper model."""
    global _whisper_model
    if _whisper_model is None:
        try:
            from faster_whisper import WhisperModel
            from backend.config import settings
            logger.info("Loading Faster Whisper model: %s", settings.whisper_model_size)
            _whisper_model = WhisperModel(
                settings.whisper_model_size,
                device=settings.whisper_device,
                compute_type=settings.whisper_compute_type,
            )
            logger.info("Faster Whisper model loaded.")
        except ImportError:
            logger.error("faster-whisper not installed. Run: pip install faster-whisper")
            raise
    return _whisper_model


# ──────────────────────────────────────────────────────────────
# Data classes
# ──────────────────────────────────────────────────────────────

@dataclass
class ASRSegment:
    text: str
    start: float
    end: float
    confidence: float            # 0.0–1.0 (derived from avg log-prob)
    language: str
    is_mixed_language: bool = False
    no_speech_prob: float = 0.0


@dataclass
class ASRResult:
    full_text: str
    segments: List[ASRSegment] = field(default_factory=list)
    detected_language: str = "unknown"
    overall_confidence: float = 0.0
    processing_time_ms: float = 0.0
    is_mixed_language: bool = False
    language_probabilities: dict = field(default_factory=dict)
    warning: Optional[str] = None


# ──────────────────────────────────────────────────────────────
# Language utilities
# ──────────────────────────────────────────────────────────────

SUPPORTED_LANGUAGES = {
    "kn": "Kannada",
    "hi": "Hindi",
    "en": "English",
    
}

MIXED_LANGUAGE_INDICATORS = [
    # Kannada + English patterns
    ("kn", "en"), ("en", "kn"),
    # Hindi + English (Hinglish)
    ("hi", "en"), ("en", "hi"),
]


def _log_prob_to_confidence(avg_log_prob: float) -> float:
    """Convert Whisper avg_log_prob to 0–1 confidence."""
    import math
    # avg_log_prob is typically in range [-2.0, 0.0]
    # Map to [0, 1]: confidence = exp(avg_log_prob) clamped
    raw = math.exp(max(avg_log_prob, -2.0))
    return round(min(max(raw, 0.0), 1.0), 4)


def _detect_mixed_language(segments) -> bool:
    """Detect if audio contains code-switching between languages."""
    if len(segments) < 2:
        return False
    # Check if consecutive segments have very different character sets
    lang_switches = 0
    prev_lang = None
    for seg in segments:
        # Simple heuristic: look for Devanagari + Latin switches
        has_devanagari = any('\u0900' <= c <= '\u097F' for c in seg.text)
        has_latin = any('a' <= c.lower() <= 'z' for c in seg.text)
        if has_devanagari and has_latin:
            lang_switches += 1
    return lang_switches > 0


# ──────────────────────────────────────────────────────────────
# Core transcription
# ──────────────────────────────────────────────────────────────

def transcribe_audio(
    audio_path: str,
    language_hint: Optional[str] = None,
    task: str = "transcribe",
) -> ASRResult:
    """
    Transcribe an audio file using Faster Whisper.

    Args:
        audio_path: Path to .wav or .mp3 file
        language_hint: Optional ISO code ('kn', 'hi', 'en')
        task: 'transcribe' or 'translate' (translate → English)

    Returns:
        ASRResult with full text, segments, and confidence scores.
    """
    start_time = time.time()
    model = get_whisper_model()

    transcribe_kwargs = {
        "beam_size": 5,
        "best_of": 5,
        "temperature": [0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
        "compression_ratio_threshold": 2.4,
        "log_prob_threshold": -1.0,
        "no_speech_threshold": 0.6,
        "condition_on_previous_text": True,
        "word_timestamps": False,
        "vad_filter": True,             # Voice activity detection — filters silence
        "vad_parameters": {
            "min_silence_duration_ms": 500,
            "speech_pad_ms": 200,
        },
        "task": task,
    }

    if language_hint:
        transcribe_kwargs["language"] = language_hint

    try:
        segments_iter, info = model.transcribe(audio_path, **transcribe_kwargs)
        segments_list = list(segments_iter)

        # Build segment objects
        processed_segments = []
        total_conf = 0.0
        for seg in segments_list:
            conf = _log_prob_to_confidence(seg.avg_logprob)
            total_conf += conf
            processed_segments.append(ASRSegment(
                text=seg.text.strip(),
                start=seg.start,
                end=seg.end,
                confidence=conf,
                language=info.language,
                no_speech_prob=seg.no_speech_prob,
            ))

        full_text = " ".join(s.text for s in processed_segments if s.text)
        avg_conf = total_conf / len(processed_segments) if processed_segments else 0.0
        is_mixed = _detect_mixed_language(processed_segments)

        elapsed_ms = (time.time() - start_time) * 1000

        return ASRResult(
            full_text=full_text,
            segments=processed_segments,
            detected_language=info.language,
            overall_confidence=round(avg_conf, 4),
            processing_time_ms=round(elapsed_ms, 1),
            is_mixed_language=is_mixed,
            language_probabilities=dict(info.all_language_probs or {}),
        )

    except Exception as exc:
        logger.error("Transcription failed for %s: %s", audio_path, exc)
        return ASRResult(
            full_text="",
            overall_confidence=0.0,
            warning=str(exc),
        )


def transcribe_bytes(audio_bytes: bytes, language_hint: Optional[str] = None) -> ASRResult:
    """
    Transcribe raw audio bytes (from microphone stream / WebSocket).
    Writes to a temp file, transcribes, then cleans up.
    """
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name
    try:
        return transcribe_audio(tmp_path, language_hint)
    finally:
        os.unlink(tmp_path)


# ──────────────────────────────────────────────────────────────
# Streaming transcription (chunked audio from WebSocket)
# ──────────────────────────────────────────────────────────────

class StreamingTranscriber:
    """
    Accumulates audio chunks and transcribes incrementally.
    Emits partial results every N seconds for real-time UI updates.
    """

    def __init__(self, chunk_duration_s: float = 3.0, language_hint: Optional[str] = None):
        self.chunk_duration_s = chunk_duration_s
        self.language_hint = language_hint
        self._buffer: bytes = b""
        self._sample_rate = 16000
        self._bytes_per_chunk = int(chunk_duration_s * self._sample_rate * 2)  # 16-bit PCM

    def feed(self, audio_chunk: bytes) -> Optional[ASRResult]:
        """
        Feed audio bytes. Returns an ASRResult when enough data accumulates.
        Returns None if still buffering.
        """
        self._buffer += audio_chunk
        if len(self._buffer) >= self._bytes_per_chunk:
            result = transcribe_bytes(self._buffer, self.language_hint)
            self._buffer = b""  # Reset buffer
            return result
        return None

    def flush(self) -> Optional[ASRResult]:
        """Transcribe any remaining buffered audio."""
        if self._buffer:
            result = transcribe_bytes(self._buffer, self.language_hint)
            self._buffer = b""
            return result
        return None
