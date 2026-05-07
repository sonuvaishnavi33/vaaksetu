import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, List, Any
from backend.config import settings

logger = logging.getLogger(__name__)


class EscalationTrigger(str, Enum):
    PANIC_DETECTED = "panic_detected"
    LOW_CONFIDENCE = "low_confidence"
    REPEATED_MISUNDERSTANDING = "repeated_misunderstanding"
    HIGH_URGENCY = "high_urgency"
    CITIZEN_REQUEST = "citizen_request"
    SYSTEM_FAILURE = "system_failure"
    EMERGENCY_SEVERITY = "emergency_severity"


class EscalationPriority(str, Enum):
    CRITICAL = "critical"    # Panic, violence, life threat
    HIGH = "high"            # Strong fear, repeated failure
    MEDIUM = "medium"        # Low confidence, confusion
    LOW = "low"              # Citizen preference, general inquiry


@dataclass
class EscalationPackage:
    """Everything an agent needs to take over the call instantly."""
    escalation_id: str
    session_id: str
    timestamp: datetime
    trigger: EscalationTrigger
    priority: EscalationPriority

    # Citizen state
    emotion: str
    urgency_score: float
    panic_detected: bool
    misunderstanding_risk: float
    confidence_at_escalation: float
    retry_count: int

    # Context
    transcript_summary: str
    ai_understood_intent: str
    issue_type: str
    language: str

    # Suggested agent action
    suggested_response: str
    critical_flags: List[str] = field(default_factory=list)
    full_transcript: List[Dict] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "escalation_id": self.escalation_id,
            "session_id": self.session_id,
            "timestamp": self.timestamp.isoformat(),
            "trigger": self.trigger,
            "priority": self.priority,
            "emotion": self.emotion,
            "urgency_score": self.urgency_score,
            "panic_detected": self.panic_detected,
            "misunderstanding_risk": self.misunderstanding_risk,
            "confidence_at_escalation": self.confidence_at_escalation,
            "retry_count": self.retry_count,
            "transcript_summary": self.transcript_summary,
            "ai_understood_intent": self.ai_understood_intent,
            "issue_type": self.issue_type,
            "language": self.language,
            "suggested_response": self.suggested_response,
            "critical_flags": self.critical_flags,
            "full_transcript": self.full_transcript,
        }


def _determine_priority(
    trigger: EscalationTrigger,
    urgency_score: float,
    panic_detected: bool,
    emotion: str,
) -> EscalationPriority:
    """Determine escalation priority based on signals."""
    if panic_detected or trigger == EscalationTrigger.PANIC_DETECTED:
        return EscalationPriority.CRITICAL
    if urgency_score >= 0.8 or emotion in ("fear", "panic"):
        return EscalationPriority.CRITICAL
    if trigger == EscalationTrigger.HIGH_URGENCY or urgency_score >= 0.6:
        return EscalationPriority.HIGH
    if trigger == EscalationTrigger.REPEATED_MISUNDERSTANDING:
        return EscalationPriority.HIGH
    if trigger == EscalationTrigger.LOW_CONFIDENCE:
        return EscalationPriority.MEDIUM
    return EscalationPriority.LOW


def _generate_suggested_response(
    issue_type: str,
    emotion: str,
    priority: EscalationPriority,
    language: str,
) -> str:
    """Generate agent suggested opening response."""
    empathy_map = {
        "panic": "I can hear you're very distressed right now. I'm here with you.",
        "fear": "You're safe to speak with me. I'm going to help you.",
        "anger": "I understand your frustration. Let me resolve this for you.",
        "sadness": "I'm sorry you're going through this. I'm here to help.",
        "confusion": "I'll help you understand what to do next, step by step.",
    }
    opening = empathy_map.get(emotion, "Thank you for calling. I'm here to help you.")

    if priority == EscalationPriority.CRITICAL:
        return f"{opening} Can you tell me your current location?"
    return f"{opening} My name is [Agent Name]. How can I assist you today?"


def should_escalate(
    emotion: str,
    urgency_score: float,
    understanding_confidence: float,
    retry_count: int,
    panic_detected: bool,
    citizen_requested: bool = False,
) -> tuple[bool, Optional[EscalationTrigger]]:
    """
    Evaluate whether escalation is needed.
    Returns (should_escalate: bool, trigger: EscalationTrigger | None)
    """
    # Immediate escalation — no questions asked
    if panic_detected:
        return True, EscalationTrigger.PANIC_DETECTED
    if citizen_requested:
        return True, EscalationTrigger.CITIZEN_REQUEST
    if urgency_score >= settings.panic_escalation_score:
        return True, EscalationTrigger.HIGH_URGENCY

    # Conditional escalation
    if retry_count >= settings.max_retry_attempts:
        return True, EscalationTrigger.REPEATED_MISUNDERSTANDING
    if understanding_confidence < settings.confidence_escalate_threshold:
        return True, EscalationTrigger.LOW_CONFIDENCE

    return False, None


def create_escalation_package(
    session_id: str,
    trigger: EscalationTrigger,
    emotion: str,
    urgency_score: float,
    panic_detected: bool,
    misunderstanding_risk: float,
    confidence: float,
    retry_count: int,
    transcript_summary: str,
    ai_intent: str,
    issue_type: str,
    language: str,
    full_transcript: List[Dict] = None,
) -> EscalationPackage:
    """Build the complete escalation package for the agent dashboard."""
    priority = _determine_priority(trigger, urgency_score, panic_detected, emotion)
    suggested = _generate_suggested_response(issue_type, emotion, priority, language)

    critical_flags = []
    if panic_detected:
        critical_flags.append("🚨 PANIC DETECTED")
    if urgency_score >= 0.8:
        critical_flags.append("⚡ HIGH URGENCY")
    if misunderstanding_risk >= 0.7:
        critical_flags.append("⚠️ HIGH MISUNDERSTANDING RISK")
    if retry_count >= 2:
        critical_flags.append(f"🔄 {retry_count} FAILED RETRIES")

    return EscalationPackage(
        escalation_id=str(uuid.uuid4()),
        session_id=session_id,
        timestamp=datetime.utcnow(),
        trigger=trigger,
        priority=priority,
        emotion=emotion,
        urgency_score=urgency_score,
        panic_detected=panic_detected,
        misunderstanding_risk=misunderstanding_risk,
        confidence_at_escalation=confidence,
        retry_count=retry_count,
        transcript_summary=transcript_summary,
        ai_understood_intent=ai_intent,
        issue_type=issue_type,
        language=language,
        suggested_response=suggested,
        critical_flags=critical_flags,
        full_transcript=full_transcript or [],
    )