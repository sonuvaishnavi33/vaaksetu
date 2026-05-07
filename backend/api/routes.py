
import uuid
import logging
import asyncio
from typing import Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.config import settings
from backend.models.session import get_db, CallSession, Transcript, UnderstandingRecord, EscalationEvent, init_db
from backend.websocket.manager import manager
from ai_pipeline.asr.whisper_engine import transcribe_bytes
from ai_pipeline.emotion.emotion_engine import analyze_emotion
from ai_pipeline.understanding.understanding_engine import understand_transcript, generate_response
from ai_pipeline.confirmation.confirmation_loop import ConfirmationEngine
from ai_pipeline.escalation.escalation_engine import should_escalate, create_escalation_package

logger = logging.getLogger(__name__)
router = APIRouter()

# Session-level confirmation engines (keyed by session_id)
_confirmation_engines: dict = {}


# ──────────────────────────────────────────────────────────────
# Request / Response schemas
# ──────────────────────────────────────────────────────────────

class TranscribeRequest(BaseModel):
    text: str
    session_id: str
    language: Optional[str] = "en"

class ConfirmRequest(BaseModel):
    session_id: str
    response: str
    language: Optional[str] = "en"

class EscalateRequest(BaseModel):
    session_id: str
    reason: str = "citizen_request"


# ──────────────────────────────────────────────────────────────
# Health & status
# ──────────────────────────────────────────────────────────────

@router.get("/health")
async def health_check():
    return {
        "status": "ok",
        "llm_provider": settings.get_active_llm(),
        "aws_configured": settings.is_aws_configured(),
        "openai_configured": settings.is_openai_configured(),
    }


@router.get("/config/status")
async def config_status():
    """Return safe config status — no secrets."""
    return settings.safe_repr()


# ──────────────────────────────────────────────────────────────
# Session management
# ──────────────────────────────────────────────────────────────

@router.post("/session/start")
async def start_session(db: Session = Depends(get_db)):
    session_id = str(uuid.uuid4())
    call = CallSession(session_id=session_id)
    db.add(call)
    db.commit()
    _confirmation_engines[session_id] = ConfirmationEngine(session_id)
    logger.info("New session started: %s", session_id)
    return {"session_id": session_id, "status": "started"}


@router.post("/session/{session_id}/end")
async def end_session(session_id: str, db: Session = Depends(get_db)):
    call = db.query(CallSession).filter_by(session_id=session_id).first()
    if call:
        from datetime import datetime
        call.end_time = datetime.utcnow()
        db.commit()
    _confirmation_engines.pop(session_id, None)
    return {"status": "ended"}


# ──────────────────────────────────────────────────────────────
# Audio upload → full AI pipeline
# ──────────────────────────────────────────────────────────────

@router.post("/process/audio")
async def process_audio(
    session_id: str,
    audio_file: UploadFile = File(...),
    language_hint: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    Full pipeline: Audio → ASR → Emotion → Understanding → Confirmation.
    Returns structured AI analysis + confirmation prompt.
    """
    audio_bytes = await audio_file.read()

    # 1. ASR
    asr_result = transcribe_bytes(audio_bytes, language_hint)

    # Save transcript
    t = Transcript(
        session_id=session_id,
        speaker="citizen",
        raw_text=asr_result.full_text,
        language=asr_result.detected_language,
        confidence=asr_result.overall_confidence,
    )
    db.add(t)

    # Emit live transcript
    await manager.emit_transcript(
        session_id, asr_result.full_text, "citizen",
        asr_result.detected_language, asr_result.overall_confidence
    )

    # 2. Emotion analysis
    emotion = analyze_emotion(
        asr_result.full_text,
        language=asr_result.detected_language,
    )

    await manager.emit_emotion_update(
        session_id, emotion.primary_emotion, emotion.urgency_score,
        emotion.panic_detected, emotion.emotion_scores
    )

    # 3. Immediate escalation check (panic override)
    needs_esc, trigger = should_escalate(
        emotion=emotion.primary_emotion,
        urgency_score=emotion.urgency_score,
        understanding_confidence=0.5,  # Not yet calculated
        retry_count=0,
        panic_detected=emotion.panic_detected,
    )
    if needs_esc and trigger in ("panic_detected", "high_urgency"):
        pkg = create_escalation_package(
            session_id=session_id,
            trigger=trigger,
            emotion=emotion.primary_emotion,
            urgency_score=emotion.urgency_score,
            panic_detected=emotion.panic_detected,
            misunderstanding_risk=0.5,
            confidence=0.0,
            retry_count=0,
            transcript_summary=asr_result.full_text,
            ai_intent="Emergency — immediate escalation",
            issue_type="emergency",
            language=asr_result.detected_language,
        )
        await manager.emit_escalation_alert(pkg.to_dict())
        return {"action": "escalate", "escalation": pkg.to_dict()}

    # 4. Understanding
    understanding = understand_transcript(
        asr_result.full_text,
        language=asr_result.detected_language,
        emotion=emotion.primary_emotion,
    )

    await manager.emit_confidence_update(
        session_id,
        understanding.understanding_confidence,
        1.0 - understanding.understanding_confidence,
        0,
    )

    # Save understanding record
    ur = UnderstandingRecord(
        session_id=session_id,
        raw_transcript=asr_result.full_text,
        intent=understanding.intent,
        issue_type=understanding.issue_type,
        emotion=emotion.primary_emotion,
        urgency_score=emotion.urgency_score,
        understanding_confidence=understanding.understanding_confidence,
        ambiguity_flags=understanding.ambiguity_flags,
    )
    db.add(ur)
    db.commit()

    # 5. Start confirmation loop
    engine = _confirmation_engines.get(session_id) or ConfirmationEngine(session_id)
    _confirmation_engines[session_id] = engine
    confirmation = engine.start_confirmation(understanding, asr_result.detected_language)

    await manager.emit_confirmation_request(
        session_id, confirmation["prompt"],
        confirmation["attempt"], confirmation["misunderstanding_risk"]
    )

    return {
        "asr": {
            "text": asr_result.full_text,
            "language": asr_result.detected_language,
            "confidence": asr_result.overall_confidence,
            "is_mixed": asr_result.is_mixed_language,
        },
        "emotion": {
            "primary": emotion.primary_emotion,
            "urgency": emotion.urgency_score,
            "panic": emotion.panic_detected,
            "scores": emotion.emotion_scores,
        },
        "understanding": {
            "intent": understanding.intent,
            "issue_type": understanding.issue_type,
            "confidence": understanding.understanding_confidence,
            "summary": understanding.confirmation_summary,
            "clarification_questions": understanding.clarification_questions,
        },
        "confirmation": confirmation,
    }


@router.post("/process/text")
async def process_text(request: TranscribeRequest, db: Session = Depends(get_db)):
    """Process pre-transcribed text through emotion → understanding → confirmation."""
    emotion = analyze_emotion(request.text, language=request.language)
    understanding = understand_transcript(request.text, language=request.language, emotion=emotion.primary_emotion)

    engine = _confirmation_engines.get(request.session_id) or ConfirmationEngine(request.session_id)
    _confirmation_engines[request.session_id] = engine
    confirmation = engine.start_confirmation(understanding, request.language)

    await manager.emit_transcript(request.session_id, request.text, "citizen", request.language, 1.0)
    await manager.emit_emotion_update(request.session_id, emotion.primary_emotion, emotion.urgency_score, emotion.panic_detected, emotion.emotion_scores)
    await manager.emit_confidence_update(request.session_id, understanding.understanding_confidence, 1.0 - understanding.understanding_confidence, 0)

    return {
        "emotion": {"primary": emotion.primary_emotion, "urgency": emotion.urgency_score, "panic": emotion.panic_detected},
        "understanding": {"intent": understanding.intent, "confidence": understanding.understanding_confidence, "summary": understanding.confirmation_summary},
        "confirmation": confirmation,
    }


@router.post("/confirm")
async def process_confirmation(request: ConfirmRequest, db: Session = Depends(get_db)):
    """Process citizen's yes/no confirmation response."""
    engine = _confirmation_engines.get(request.session_id)
    if not engine:
        raise HTTPException(404, "No active session")

    result = engine.process_response(request.response, request.language)

    if result.get("next_action") == "escalate":
        await manager.emit_escalation_alert({
            "session_id": request.session_id,
            "trigger": "repeated_misunderstanding",
            "message": result.get("message", ""),
        })

    return result


@router.post("/escalate")
async def manual_escalate(request: EscalateRequest, db: Session = Depends(get_db)):
    """Manually trigger escalation (citizen request or agent override)."""
    pkg = create_escalation_package(
        session_id=request.session_id,
        trigger=request.reason,
        emotion="unknown", urgency_score=0.5, panic_detected=False,
        misunderstanding_risk=0.5, confidence=0.5, retry_count=0,
        transcript_summary="Manual escalation requested",
        ai_intent="Manual override",
        issue_type="general_inquiry", language="en",
    )
    await manager.emit_escalation_alert(pkg.to_dict())
    return {"status": "escalated", "escalation_id": pkg.escalation_id}


@router.get("/sessions/{session_id}/transcript")
async def get_transcript(session_id: str, db: Session = Depends(get_db)):
    records = db.query(Transcript).filter_by(session_id=session_id).order_by(Transcript.timestamp).all()
    return [{"speaker": r.speaker, "text": r.raw_text, "language": r.language, "timestamp": r.timestamp.isoformat()} for r in records]


@router.get("/analytics/summary")
async def analytics_summary(db: Session = Depends(get_db)):
    total = db.query(CallSession).count()
    escalated = db.query(CallSession).filter_by(escalated=True).count()
    return {
        "total_sessions": total,
        "escalated": escalated,
        "escalation_rate": round(escalated / max(total, 1), 3),
    }


# ──────────────────────────────────────────────────────────────
# WebSocket endpoints
# ──────────────────────────────────────────────────────────────

@router.websocket("/ws/session/{session_id}")
async def caller_websocket(websocket: WebSocket, session_id: str):
    """WebSocket for caller-facing real-time updates."""
    await manager.connect_caller(websocket, session_id)
    try:
        while True:
            data = await websocket.receive_json()
            # Handle audio chunks or text
            if data.get("type") == "audio_chunk":
                audio = bytes.fromhex(data.get("data", ""))
                asr = transcribe_bytes(audio)
                if asr.full_text:
                    await manager.emit_transcript(session_id, asr.full_text, "citizen", asr.detected_language, asr.overall_confidence)
            elif data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        manager.disconnect_caller(websocket, session_id)


@router.websocket("/ws/agent")
async def agent_websocket(websocket: WebSocket):
    """WebSocket for agent dashboard — receives all escalation events."""
    await manager.connect_agent(websocket)
    try:
        while True:
            data = await websocket.receive_json()
            if data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        manager.disconnect_agent(websocket)


@router.websocket("/ws/analytics")
async def analytics_websocket(websocket: WebSocket):
    """WebSocket for analytics dashboard."""
    await manager.connect_analytics(websocket)
    try:
        while True:
            await websocket.receive_json()
    except WebSocketDisconnect:
        pass
