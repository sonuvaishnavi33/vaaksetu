
import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, List, Set, Optional
from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    Manages all active WebSocket connections.
    Supports per-session rooms and broadcast channels.
    """

    def __init__(self):
        # session_id → list of active WebSocket connections
        self._sessions: Dict[str, List[WebSocket]] = {}
        # Agent dashboard connections (receive all escalation events)
        self._agents: Set[WebSocket] = set()
        # Analytics connections
        self._analytics: Set[WebSocket] = set()

    # ── Connection lifecycle ───────────────────────────────────

    async def connect_caller(self, websocket: WebSocket, session_id: str):
        await websocket.accept()
        if session_id not in self._sessions:
            self._sessions[session_id] = []
        self._sessions[session_id].append(websocket)
        logger.info("Caller WS connected: session=%s", session_id)

    async def connect_agent(self, websocket: WebSocket):
        await websocket.accept()
        self._agents.add(websocket)
        logger.info("Agent dashboard WS connected. Total agents: %d", len(self._agents))

    async def connect_analytics(self, websocket: WebSocket):
        await websocket.accept()
        self._analytics.add(websocket)

    def disconnect_caller(self, websocket: WebSocket, session_id: str):
        if session_id in self._sessions:
            self._sessions[session_id] = [
                ws for ws in self._sessions[session_id] if ws != websocket
            ]
            if not self._sessions[session_id]:
                del self._sessions[session_id]
        logger.info("Caller WS disconnected: session=%s", session_id)

    def disconnect_agent(self, websocket: WebSocket):
        self._agents.discard(websocket)

    # ── Messaging ─────────────────────────────────────────────

    async def _safe_send(self, websocket: WebSocket, message: dict):
        """Send JSON message, handling disconnection gracefully."""
        try:
            await websocket.send_json(message)
        except Exception as exc:
            logger.warning("WS send failed: %s", exc)

    async def send_to_session(self, session_id: str, message: dict):
        """Send message to all connections in a session."""
        for ws in self._sessions.get(session_id, []):
            await self._safe_send(ws, message)

    async def broadcast_to_agents(self, message: dict):
        """Send message to all connected agent dashboards."""
        disconnected = set()
        for ws in self._agents:
            try:
                await ws.send_json(message)
            except Exception:
                disconnected.add(ws)
        self._agents -= disconnected

    async def broadcast_to_analytics(self, message: dict):
        """Send message to analytics dashboard."""
        disconnected = set()
        for ws in self._analytics:
            try:
                await ws.send_json(message)
            except Exception:
                disconnected.add(ws)
        self._analytics -= disconnected

    # ── Typed event emitters ───────────────────────────────────

    async def emit_transcript(self, session_id: str, text: str, speaker: str,
                               language: str, confidence: float):
        """Emit a new transcript segment."""
        event = {
            "type": "transcript",
            "session_id": session_id,
            "text": text,
            "speaker": speaker,
            "language": language,
            "confidence": confidence,
            "timestamp": datetime.utcnow().isoformat(),
        }
        await self.send_to_session(session_id, event)
        await self.broadcast_to_agents(event)

    async def emit_emotion_update(self, session_id: str, emotion: str,
                                   urgency: float, panic: bool, scores: dict):
        """Emit emotion/urgency state update."""
        event = {
            "type": "emotion_update",
            "session_id": session_id,
            "emotion": emotion,
            "urgency_score": urgency,
            "panic_detected": panic,
            "scores": scores,
            "timestamp": datetime.utcnow().isoformat(),
        }
        await self.send_to_session(session_id, event)
        await self.broadcast_to_agents(event)

    async def emit_confidence_update(self, session_id: str, confidence: float,
                                      misunderstanding_risk: float, retry_count: int):
        """Emit AI understanding confidence update."""
        event = {
            "type": "confidence_update",
            "session_id": session_id,
            "confidence": confidence,
            "misunderstanding_risk": misunderstanding_risk,
            "retry_count": retry_count,
            "timestamp": datetime.utcnow().isoformat(),
        }
        await self.send_to_session(session_id, event)
        await self.broadcast_to_agents(event)

    async def emit_escalation_alert(self, escalation_package: dict):
        """Emit high-priority escalation to agent dashboard."""
        event = {
            "type": "escalation_alert",
            **escalation_package,
            "timestamp": datetime.utcnow().isoformat(),
        }
        await self.broadcast_to_agents(event)
        # Also send to analytics
        await self.broadcast_to_analytics({
            "type": "escalation_stats",
            "session_id": escalation_package.get("session_id"),
            "priority": escalation_package.get("priority"),
            "trigger": escalation_package.get("trigger"),
            "timestamp": datetime.utcnow().isoformat(),
        })

    async def emit_confirmation_request(self, session_id: str, prompt: str,
                                         attempt: int, misunderstanding_risk: float):
        """Emit a confirmation request to the caller interface."""
        event = {
            "type": "confirmation_request",
            "session_id": session_id,
            "prompt": prompt,
            "attempt": attempt,
            "misunderstanding_risk": misunderstanding_risk,
            "timestamp": datetime.utcnow().isoformat(),
        }
        await self.send_to_session(session_id, event)


# Shared connection manager instance for the application.
manager = ConnectionManager()

