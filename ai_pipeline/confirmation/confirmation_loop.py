import logging
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Dict
from backend.config import settings
from ai_pipeline.understanding.understanding_engine import UnderstandingResult

logger = logging.getLogger(__name__)


class ConfirmationState(str, Enum):
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    RETRY = "retry"
    ESCALATE = "escalate"
    TIMED_OUT = "timed_out"


@dataclass
class ConfirmationSession:
    """State machine for one confirmation exchange."""
    session_id: str
    understanding: UnderstandingResult
    attempt_number: int = 1              # Which retry we're on
    state: ConfirmationState = ConfirmationState.AWAITING_CONFIRMATION
    history: List[Dict] = field(default_factory=list)
    misunderstanding_risk: float = 0.0
    should_escalate: bool = False
    escalation_reason: str = ""


# ──────────────────────────────────────────────────────────────
# Confirmation prompt templates (multilingual)
# ──────────────────────────────────────────────────────────────

CONFIRMATION_TEMPLATES = {
    "en": {
        "confirm": "I understood that {summary}. Is that correct? Please say YES or NO.",
        "retry_1": "Let me try again. Did you mean {summary}? Please say YES if correct, or NO to explain more.",
        "retry_2": "I'm still not sure I understand correctly. {summary} — is this right? If not, please tell me more.",
        "escalate": "I want to make sure you get the right help. Let me connect you to a person who can assist you better.",
    },
    "hi": {
        "confirm": "मैंने समझा कि {summary}। क्या यह सही है? कृपया हाँ या नहीं कहें।",
        "retry_1": "मुझे फिर से समझाइए। क्या आपका मतलब {summary} था? सही होने पर हाँ, अन्यथा नहीं कहें।",
        "retry_2": "मैं अभी भी पूरी तरह नहीं समझ पाया। {summary} — क्या यह सही है?",
        "escalate": "आपकी बेहतर सहायता के लिए मैं एक इंसान से जोड़ रहा हूँ।",
    },
    "kn": {
        "confirm": "ನಾನು ಅರ್ಥ ಮಾಡಿಕೊಂಡೆ: {summary}. ಇದು ಸರಿಯೇ? ಹೌದು ಅಥವಾ ಇಲ್ಲ ಎಂದು ಹೇಳಿ.",
        "retry_1": "ದಯವಿಟ್ಟು ಮತ್ತೆ ಹೇಳಿ. {summary} - ಇದು ಸರಿಯೇ?",
        "retry_2": "ನನಗೆ ಇನ್ನೂ ಸ್ಪಷ್ಟವಾಗಿಲ್ಲ. {summary} - ಹೌದೇ?",
        "escalate": "ನಿಮಗೆ ಉತ್ತಮ ಸಹಾಯ ಮಾಡಲು ನಾನು ಒಬ್ಬ ವ್ಯಕ್ತಿಗೆ ಸಂಪರ್ಕಿಸುತ್ತೇನೆ.",
    },
}

AFFIRMATIVE_WORDS = {
    "en": ["yes", "correct", "right", "yeah", "yep", "sure", "ok", "okay", "confirmed", "that's right"],
    "hi": ["haan", "ha", "sahi", "theek", "bilkul", "haan ji", "ji haan"],
    "kn": ["haudu", "sari", "haan", "correct", "yes"],
}

NEGATIVE_WORDS = {
    "en": ["no", "nope", "wrong", "incorrect", "not right", "that's wrong", "nahi"],
    "hi": ["nahi", "nahin", "galat", "nhin", "no"],
    "kn": ["illa", "thappu", "no", "nahi"],
}


def get_confirmation_prompt(
    understanding: UnderstandingResult,
    attempt: int,
    language: str = "en",
) -> str:
    """Get the right confirmation prompt for the attempt number."""
    lang = language if language in CONFIRMATION_TEMPLATES else "en"
    templates = CONFIRMATION_TEMPLATES[lang]
    summary = understanding.confirmation_summary or understanding.primary_concern

    if attempt == 1:
        key = "confirm"
    elif attempt == 2:
        key = "retry_1"
    elif attempt == 3:
        key = "retry_2"
    else:
        key = "escalate"

    return templates[key].format(summary=summary)


def parse_citizen_response(
    response: str,
    language: str = "en",
) -> Optional[bool]:
    """
    Parse citizen's yes/no response.
    Returns True (confirmed), False (rejected), None (unclear).
    """
    response_lower = response.lower().strip()

    # Check affirmative
    for lang_words in AFFIRMATIVE_WORDS.values():
        if any(word in response_lower for word in lang_words):
            return True

    # Check negative
    for lang_words in NEGATIVE_WORDS.values():
        if any(word in response_lower for word in lang_words):
            return False

    return None  # Unclear — treat as rejection for safety


def calculate_misunderstanding_risk(
    understanding: UnderstandingResult,
    attempt_number: int,
) -> float:
    """
    Calculate probability that AI has misunderstood the citizen.
    Used to prioritise escalation decisions.
    """
    base_risk = 1.0 - understanding.understanding_confidence

    # Increase risk per retry
    retry_penalty = (attempt_number - 1) * 0.15

    # Increase risk for ambiguous input
    if understanding.is_ambiguous:
        base_risk += 0.1

    # Increase risk for mixed language
    if understanding.is_mixed_language:
        base_risk += 0.05

    # Increase risk for short transcripts
    if len(understanding.intent) < 20:
        base_risk += 0.1

    return round(min(base_risk + retry_penalty, 1.0), 4)


# ──────────────────────────────────────────────────────────────
# Main confirmation engine
# ──────────────────────────────────────────────────────────────

class ConfirmationEngine:
    """
    Manages the confirmation loop for a single call session.
    Tracks state across multiple turns.
    """

    def __init__(self, session_id: str):
        self.session_id = session_id
        self._sessions: Dict[str, ConfirmationSession] = {}

    def start_confirmation(
        self,
        understanding: UnderstandingResult,
        language: str = "en",
    ) -> Dict:
        """
        Initiate a new confirmation exchange.
        Returns the prompt to speak to the citizen.
        """
        conf_session = ConfirmationSession(
            session_id=self.session_id,
            understanding=understanding,
            attempt_number=1,
        )
        conf_session.misunderstanding_risk = calculate_misunderstanding_risk(
            understanding, 1
        )
        self._sessions[self.session_id] = conf_session

        prompt = get_confirmation_prompt(understanding, 1, language)

        return {
            "prompt": prompt,
            "state": ConfirmationState.AWAITING_CONFIRMATION,
            "attempt": 1,
            "misunderstanding_risk": conf_session.misunderstanding_risk,
            "max_attempts": settings.max_retry_attempts,
        }

    def process_response(
        self,
        citizen_response: str,
        language: str = "en",
    ) -> Dict:
        """
        Process citizen's yes/no response and advance state machine.

        Returns:
            Dict with next_action, prompt (if retry), and escalation flag.
        """
        conf_session = self._sessions.get(self.session_id)
        if not conf_session:
            return {
                "next_action": "error",
                "message": "No active confirmation session.",
            }

        # Log this response
        conf_session.history.append({
            "attempt": conf_session.attempt_number,
            "response": citizen_response,
        })

        # Parse response
        confirmed = parse_citizen_response(citizen_response, language)

        if confirmed is True:
            # ✅ Confirmed — proceed
            conf_session.state = ConfirmationState.CONFIRMED
            return {
                "next_action": "proceed",
                "state": ConfirmationState.CONFIRMED,
                "confirmed_understanding": conf_session.understanding,
                "attempt": conf_session.attempt_number,
            }

        elif confirmed is False or confirmed is None:
            # ❌ Rejected or unclear
            conf_session.attempt_number += 1
            conf_session.misunderstanding_risk = calculate_misunderstanding_risk(
                conf_session.understanding, conf_session.attempt_number
            )

            if conf_session.attempt_number > settings.max_retry_attempts:
                # 🚨 Too many retries — escalate
                conf_session.state = ConfirmationState.ESCALATE
                conf_session.should_escalate = True
                conf_session.escalation_reason = "repeated_misunderstanding"
                escalation_msg = CONFIRMATION_TEMPLATES.get(
                    language, CONFIRMATION_TEMPLATES["en"]
                )["escalate"].format(summary="")

                return {
                    "next_action": "escalate",
                    "state": ConfirmationState.ESCALATE,
                    "escalation_reason": "repeated_misunderstanding",
                    "message": escalation_msg,
                    "attempt": conf_session.attempt_number,
                    "misunderstanding_risk": conf_session.misunderstanding_risk,
                }

            # 🔄 Retry with clearer prompt
            conf_session.state = ConfirmationState.RETRY
            retry_prompt = get_confirmation_prompt(
                conf_session.understanding,
                conf_session.attempt_number,
                language,
            )

            return {
                "next_action": "retry",
                "state": ConfirmationState.RETRY,
                "prompt": retry_prompt,
                "attempt": conf_session.attempt_number,
                "misunderstanding_risk": conf_session.misunderstanding_risk,
            }