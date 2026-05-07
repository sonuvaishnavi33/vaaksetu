

import logging
from dataclasses import dataclass, field
from typing import Optional, Dict, List
from backend.core.llm_router import invoke_llm_json
from backend.config import settings

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
# Emotion taxonomy
# ──────────────────────────────────────────────────────────────

EMOTION_LABELS = ["fear", "panic", "anger", "confusion", "sadness", "urgency", "calm", "neutral"]

ESCALATION_EMOTIONS = {"panic", "fear", "urgency"}  # These override confidence thresholds


@dataclass
class EmotionResult:
    primary_emotion: str = "neutral"
    emotion_scores: Dict[str, float] = field(default_factory=dict)
    urgency_score: float = 0.0           # 0.0–1.0
    panic_detected: bool = False
    requires_immediate_escalation: bool = False
    confidence: float = 0.0              # Confidence in this emotion reading
    reasoning: str = ""
    raw_indicators: List[str] = field(default_factory=list)  # What triggered the detection


# ──────────────────────────────────────────────────────────────
# System prompt for emotion analysis
# ──────────────────────────────────────────────────────────────

EMOTION_SYSTEM_PROMPT = """You are an expert emotion analyst for a government emergency helpline.
Analyze the caller's speech/text and identify their emotional state with high accuracy.

Your analysis informs whether a citizen needs IMMEDIATE human assistance.
False negatives (missing panic/fear) are MUCH worse than false positives.
When in doubt, score emotions higher to protect citizen safety.

Emotional states to detect:
- fear: Feels threatened, unsafe, scared
- panic: Extreme distress, irrational, overwhelmed
- anger: Frustrated, hostile, demanding
- confusion: Disoriented, unclear thinking
- sadness: Grief, despair, helplessness
- urgency: Time-sensitive situation
- calm: Composed, matter-of-fact
- neutral: Standard informational call

Context: This is an Indian government helpline. Callers may use:
- Kannada, Hindi, English, or code-switching
- Indirect expressions of distress (cultural norms)
- Understatement (Indian cultural tendency to minimize problems)
Score these conservatively — if they say "little problem" it may be serious.

Return ONLY valid JSON. No markdown."""

EMOTION_USER_TEMPLATE = """Analyze emotion in this caller message:
"{transcript}"

Context:
- Previous emotion: {previous_emotion}
- Language: {language}
- Issue type: {issue_type}

Return JSON with exactly this structure:
{{
  "primary_emotion": "one of: fear|panic|anger|confusion|sadness|urgency|calm|neutral",
  "emotion_scores": {{
    "fear": 0.0,
    "panic": 0.0,
    "anger": 0.0,
    "confusion": 0.0,
    "sadness": 0.0,
    "urgency": 0.0,
    "calm": 0.0,
    "neutral": 0.0
  }},
  "urgency_score": 0.0,
  "panic_detected": false,
  "requires_immediate_escalation": false,
  "confidence": 0.0,
  "reasoning": "Brief explanation",
  "raw_indicators": ["list", "of", "specific", "words/phrases", "that", "triggered", "detection"]
}}"""


def analyze_emotion(
    transcript: str,
    language: str = "unknown",
    issue_type: str = "unknown",
    previous_emotion: str = "neutral",
) -> EmotionResult:
    """
    Analyze emotion from transcript text using LLM.

    Args:
        transcript: What the citizen said
        language: Detected language code
        issue_type: Type of issue (theft, harassment, etc.)
        previous_emotion: Previous emotion for context continuity

    Returns:
        EmotionResult with detailed emotion breakdown
    """
    if not transcript or not transcript.strip():
        return EmotionResult(primary_emotion="neutral", confidence=1.0)

    prompt = EMOTION_USER_TEMPLATE.format(
        transcript=transcript,
        previous_emotion=previous_emotion,
        language=language,
        issue_type=issue_type,
    )

    try:
        result = invoke_llm_json(
            messages=[{"role": "user", "content": prompt}],
            system_prompt=EMOTION_SYSTEM_PROMPT,
            max_tokens=512,
        )

        emotion = EmotionResult(
            primary_emotion=result.get("primary_emotion", "neutral"),
            emotion_scores=result.get("emotion_scores", {}),
            urgency_score=float(result.get("urgency_score", 0.0)),
            panic_detected=bool(result.get("panic_detected", False)),
            requires_immediate_escalation=bool(result.get("requires_immediate_escalation", False)),
            confidence=float(result.get("confidence", 0.0)),
            reasoning=result.get("reasoning", ""),
            raw_indicators=result.get("raw_indicators", []),
        )

        # Safety override: if panic score is high, force escalation flag
        panic_score = emotion.emotion_scores.get("panic", 0.0)
        fear_score = emotion.emotion_scores.get("fear", 0.0)
        if panic_score >= settings.panic_escalation_score or fear_score >= 0.80:
            emotion.requires_immediate_escalation = True
            emotion.panic_detected = True

        return emotion

    except Exception as exc:
        logger.error("Emotion analysis failed: %s", exc)
        # Safe fallback — treat as moderate urgency
        return EmotionResult(
            primary_emotion="unknown",
            urgency_score=0.5,
            confidence=0.0,
            reasoning=f"Analysis failed: {exc}",
        )


def merge_emotion_signals(
    text_emotion: EmotionResult,
    acoustic_emotion: Optional[Dict] = None,
) -> EmotionResult:
    """
    Merge text-based and acoustic (SenseVoice) emotion signals.
    Text emotion is primary; acoustic provides corroboration.
    """
    if acoustic_emotion is None:
        return text_emotion

    # Boost urgency if acoustic confirms
    acoustic_urgency = acoustic_emotion.get("urgency", 0.0)
    merged_urgency = max(text_emotion.urgency_score, acoustic_urgency * 0.7)

    # If acoustic detects panic but text doesn't, trust acoustic
    if acoustic_emotion.get("panic", 0.0) > 0.8 and not text_emotion.panic_detected:
        text_emotion.panic_detected = True
        text_emotion.requires_immediate_escalation = True
        text_emotion.raw_indicators.append("acoustic_panic_signal")

    text_emotion.urgency_score = round(merged_urgency, 4)
    return text_emotion
