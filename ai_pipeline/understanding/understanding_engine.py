import logging
from dataclasses import dataclass, field
from typing import Optional, List, Dict
from backend.core.llm_router import invoke_llm_json
from backend.config import settings

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
# Issue taxonomy for Indian government helplines
# ──────────────────────────────────────────────────────────────

ISSUE_TYPES = [
    "theft", "robbery", "harassment", "assault",
    "domestic_violence", "accident", "fire", "medical_emergency",
    "missing_person", "noise_complaint", "fraud", "cybercrime",
    "natural_disaster", "infrastructure_failure", "corruption",
    "general_inquiry", "unclear"
]


@dataclass
class UnderstandingResult:
    """Complete understanding of what a citizen said."""

    # Core understanding
    intent: str = ""
    issue_type: str = "unclear"
    primary_concern: str = ""
    secondary_concerns: List[str] = field(default_factory=list)

    # Confidence
    understanding_confidence: float = 0.0    # 0.0–1.0
    is_confident_enough: bool = False        # >= RETRY threshold

    # Ambiguity analysis
    is_ambiguous: bool = True
    ambiguity_flags: List[str] = field(default_factory=list)
    missing_information: List[str] = field(default_factory=list)

    # Context
    emotion: str = "neutral"
    urgency_score: float = 0.0
    language_used: str = "unknown"
    is_mixed_language: bool = False

    # Clarification
    needs_clarification: bool = True
    clarification_questions: List[str] = field(default_factory=list)
    confirmation_summary: str = ""

    # Safety
    hallucination_risk: str = "low"    # low | medium | high
    reasoning: str = ""
    raw_response: dict = field(default_factory=dict)


# ──────────────────────────────────────────────────────────────
# System prompt — the most important prompt in the system
# ──────────────────────────────────────────────────────────────

UNDERSTANDING_SYSTEM_PROMPT = """You are the understanding engine for VaakSetu, an AI assistant
for Indian government emergency helplines (like 112, 1090, etc.).

YOUR PRIMARY JOB: Understand what the citizen ACTUALLY means, not just what they literally said.

CRITICAL RULES:
1. NEVER assume. If something is unclear, set ambiguity flag and ask.
2. NEVER fill in missing details by guessing — this can cause dangerous miscommunication.
3. Citizens may speak in Kannada, Hindi, English, or mix languages.
4. Indian cultural norms mean citizens often understate urgency or speak indirectly.
5. Low confidence = you MUST ask clarification before responding substantively.

HALLUCINATION PREVENTION:
- If transcript is very short (<5 words): confidence <= 0.4
- If transcript contains only emotion markers (crying, screaming): confidence <= 0.3
- If transcript has severe noise artifacts: confidence <= 0.5
- Never infer specific addresses/names/dates not explicitly mentioned.

CONFIDENCE SCALE:
- 0.0–0.44: Very uncertain. Definitely ask clarification.
- 0.45–0.64: Partially understood. Ask 1-2 targeted questions.
- 0.65–0.79: Reasonably confident. Confirm understanding.
- 0.80–1.00: High confidence. Proceed with care.

Return ONLY valid JSON."""

UNDERSTANDING_USER_TEMPLATE = """Analyze this citizen call transcript:

TRANSCRIPT: "{transcript}"
LANGUAGE: {language}
EMOTION STATE: {emotion}
CALL HISTORY SUMMARY: {history_summary}

Return JSON with this EXACT structure:
{{
  "intent": "one sentence describing what the citizen wants",
  "issue_type": "one of: {issue_types}",
  "primary_concern": "the main problem in plain language",
  "secondary_concerns": ["list", "of", "other", "concerns"],
  "understanding_confidence": 0.0,
  "is_ambiguous": true,
  "ambiguity_flags": ["what", "is", "unclear"],
  "missing_information": ["what", "info", "is", "needed"],
  "urgency_score": 0.0,
  "needs_clarification": true,
  "clarification_questions": ["up to 2 simple questions in {language} or English"],
  "confirmation_summary": "Short summary to read back to citizen for confirmation",
  "hallucination_risk": "low|medium|high",
  "reasoning": "Internal reasoning about confidence level"
}}"""


def understand_transcript(
    transcript: str,
    language: str = "en",
    emotion: str = "neutral",
    history_summary: str = "First contact",
) -> UnderstandingResult:
    """
    Deeply understand citizen speech.

    Args:
        transcript: ASR output text
        language: Detected language ('kn', 'hi', 'en')
        emotion: Current emotion label
        history_summary: Summary of conversation so far

    Returns:
        UnderstandingResult with intent, confidence, and clarifications
    """
    if not transcript.strip():
        return UnderstandingResult(
            intent="Empty transcript",
            understanding_confidence=0.0,
            is_confident_enough=False,
            needs_clarification=True,
            clarification_questions=["Could you please speak again? I didn't catch that."],
        )

    prompt = UNDERSTANDING_USER_TEMPLATE.format(
        transcript=transcript,
        language=language,
        emotion=emotion,
        history_summary=history_summary,
        issue_types=", ".join(ISSUE_TYPES),
    )

    try:
        result = invoke_llm_json(
            messages=[{"role": "user", "content": prompt}],
            system_prompt=UNDERSTANDING_SYSTEM_PROMPT,
            max_tokens=1024,
        )

        confidence = float(result.get("understanding_confidence", 0.0))
        is_confident = confidence >= settings.confidence_retry_threshold

        return UnderstandingResult(
            intent=result.get("intent", ""),
            issue_type=result.get("issue_type", "unclear"),
            primary_concern=result.get("primary_concern", ""),
            secondary_concerns=result.get("secondary_concerns", []),
            understanding_confidence=round(confidence, 4),
            is_confident_enough=is_confident,
            is_ambiguous=result.get("is_ambiguous", True),
            ambiguity_flags=result.get("ambiguity_flags", []),
            missing_information=result.get("missing_information", []),
            emotion=emotion,
            urgency_score=float(result.get("urgency_score", 0.0)),
            language_used=language,
            needs_clarification=result.get("needs_clarification", True),
            clarification_questions=result.get("clarification_questions", []),
            confirmation_summary=result.get("confirmation_summary", ""),
            hallucination_risk=result.get("hallucination_risk", "medium"),
            reasoning=result.get("reasoning", ""),
            raw_response=result,
        )

    except Exception as exc:
        logger.error("Understanding engine failed: %s", exc)
        return UnderstandingResult(
            intent="Analysis failed",
            understanding_confidence=0.0,
            is_confident_enough=False,
            needs_clarification=True,
            clarification_questions=["I'm having trouble understanding. Could you repeat that?"],
            reasoning=str(exc),
        )


# ──────────────────────────────────────────────────────────────
# Response generation (only after understanding confirmed)
# ──────────────────────────────────────────────────────────────

RESPONSE_SYSTEM_PROMPT = """You are a compassionate, professional AI assistant for Indian government
emergency helplines. Generate responses ONLY after citizen understanding is confirmed.

Rules:
- Be warm, calm, and reassuring
- Use the citizen's language (Kannada/Hindi/English)
- Never promise outcomes you cannot guarantee
- For emergencies: always confirm help is being dispatched
- Keep responses SHORT — max 2-3 sentences for voice output
- End with next step or what to expect
"""

def generate_response(
    understanding: UnderstandingResult,
    confirmed: bool = False,
    language: str = "en",
) -> str:
    """Generate a response only when understanding is confirmed."""
    if not confirmed:
        return "I want to make sure I understand correctly before helping you."

    prompt = f"""Generate a brief, helpful response for this confirmed understanding:
Issue: {understanding.primary_concern}
Issue Type: {understanding.issue_type}
Emotion: {understanding.emotion}
Urgency: {understanding.urgency_score}
Language: {language}

Keep it under 3 sentences. Be warm and action-oriented."""

    try:
        from backend.core.llm_router import invoke_llm
        return invoke_llm(
            messages=[{"role": "user", "content": prompt}],
            system_prompt=RESPONSE_SYSTEM_PROMPT,
            max_tokens=256,
        )
    except Exception as exc:
        logger.error("Response generation failed: %s", exc)
        return "I understand your concern and am connecting you with the right help."
