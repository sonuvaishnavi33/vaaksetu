
import os
import logging
from functools import lru_cache
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

# Locate the .env file relative to this file's parent directory
ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    """
    Single source of truth for every configuration value.
    Values are loaded from environment variables / .env file.
    Secrets are NEVER logged or exposed.
    """

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── AWS ──────────────────────────────────────────────────
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_region: str = "ap-south-1"

    # ── Bedrock ──────────────────────────────────────────────
    bedrock_model_id: str = "anthropic.claude-3-sonnet-20240229-v1:0"
    bedrock_max_tokens: int = 2048
    bedrock_temperature: float = 0.2

    # ── OpenAI fallback ──────────────────────────────────────
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"

    # ── Application ───────────────────────────────────────────
    app_env: str = "development"
    debug: bool = True
    log_level: str = "INFO"
    app_port: int = 8000
    frontend_port: int = 8501

    # ── Database ─────────────────────────────────────────────
    database_url: str = "sqlite:///./vaaksetu.db"

    # ── Whisper / ASR ────────────────────────────────────────
    whisper_model_size: str = "medium"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"

    # ── Confidence & Escalation ──────────────────────────────
    confidence_escalate_threshold: float = 0.45
    confidence_retry_threshold: float = 0.65
    max_retry_attempts: int = 3
    panic_escalation_score: float = 0.75

    # ── TTS ──────────────────────────────────────────────────
    tts_rate: int = 155
    tts_volume: float = 0.95
    tts_voice_index: int = 0

    # ── WebSocket ────────────────────────────────────────────
    ws_heartbeat_interval: int = 30
    ws_reconnect_attempts: int = 5

    def is_aws_configured(self) -> bool:
        return bool(self.aws_access_key_id and self.aws_secret_access_key)

    def is_openai_configured(self) -> bool:
        return bool(self.openai_api_key)

    def get_active_llm(self) -> str:
        if self.is_aws_configured():
            return "bedrock"
        if self.is_openai_configured():
            return "openai"
        return "none"

    def safe_repr(self) -> dict:
        """Return config dict with secrets masked — safe for logging."""
        return {
            "aws_region": self.aws_region,
            "aws_configured": self.is_aws_configured(),
            "bedrock_model_id": self.bedrock_model_id,
            "openai_configured": self.is_openai_configured(),
            "active_llm": self.get_active_llm(),
            "app_env": self.app_env,
            "whisper_model_size": self.whisper_model_size,
            "confidence_escalate_threshold": self.confidence_escalate_threshold,
            "confidence_retry_threshold": self.confidence_retry_threshold,
        }


@lru_cache()
def get_settings() -> Settings:
    """Return cached singleton Settings instance."""
    settings = Settings()
    logging.getLogger(__name__).info(
        "VaakSetu config loaded: %s", settings.safe_repr()
    )
    return settings

settings = Settings()
