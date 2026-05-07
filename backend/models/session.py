from datetime import datetime
from sqlalchemy import (
    create_engine, Column, Integer, String, Float, 
    DateTime, Text, Boolean, JSON
)
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from backend.config import settings

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


class CallSession(Base):
    __tablename__ = "call_sessions"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(64), unique=True, index=True, nullable=False)
    start_time = Column(DateTime, default=datetime.utcnow)
    end_time = Column(DateTime, nullable=True)
    language_detected = Column(String(32), default="unknown")
    final_emotion = Column(String(32), default="neutral")
    final_urgency = Column(Float, default=0.0)
    escalated = Column(Boolean, default=False)
    escalation_reason = Column(String(256), nullable=True)
    total_retries = Column(Integer, default=0)
    resolved = Column(Boolean, default=False)


class Transcript(Base):
    __tablename__ = "transcripts"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(64), index=True, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    speaker = Column(String(16))          # "citizen" | "ai" | "agent"
    raw_text = Column(Text)
    language = Column(String(32))
    confidence = Column(Float, default=0.0)


class UnderstandingRecord(Base):
    __tablename__ = "understanding_records"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(64), index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    raw_transcript = Column(Text)
    intent = Column(String(128))
    issue_type = Column(String(64))
    emotion = Column(String(32))
    urgency_score = Column(Float)
    understanding_confidence = Column(Float)
    ambiguity_flags = Column(JSON)
    retry_count = Column(Integer, default=0)
    confirmed = Column(Boolean, default=False)


class EscalationEvent(Base):
    __tablename__ = "escalation_events"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(64), index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    trigger_reason = Column(String(64))
    emotion_at_escalation = Column(String(32))
    urgency_at_escalation = Column(Float)
    confidence_at_escalation = Column(Float)
    ai_summary = Column(Text)
    assigned_agent_id = Column(String(64), nullable=True)
    resolved_by_agent = Column(Boolean, default=False)


def init_db():
    """Create all tables if they don't exist."""
    Base.metadata.create_all(bind=engine)


def get_db():
    """FastAPI dependency — yields a DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
