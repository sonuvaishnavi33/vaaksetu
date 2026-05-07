
import json
import logging
from typing import List, Dict, Optional
from backend.config import settings
from backend.core.bedrock_client import invoke_bedrock

logger = logging.getLogger(__name__)


def _invoke_openai(messages: List[Dict], system_prompt: str, max_tokens: int) -> Optional[str]:
    """OpenAI fallback. Only used when Bedrock is unavailable."""
    if not settings.is_openai_configured():
        return None
    try:
        from openai import OpenAI
        client = OpenAI(api_key=settings.openai_api_key)
        all_messages = []
        if system_prompt:
            all_messages.append({"role": "system", "content": system_prompt})
        all_messages.extend(messages)
        resp = client.chat.completions.create(
            model=settings.openai_model,
            messages=all_messages,
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content
    except Exception as exc:
        logger.error("OpenAI fallback error: %s", exc)
        return None


def invoke_llm(
    messages: List[Dict],
    system_prompt: str = "",
    max_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
) -> str:
    """
    Route LLM calls: Bedrock → OpenAI → Error.
    Returns response text; raises RuntimeError if all providers fail.
    """
    mt = max_tokens or settings.bedrock_max_tokens

    # Try Bedrock (primary)
    if settings.is_aws_configured():
        result = invoke_bedrock(messages, system_prompt, mt, temperature)
        if result:
            return result
        logger.warning("Bedrock failed, attempting OpenAI fallback.")

    # Try OpenAI (fallback)
    result = _invoke_openai(messages, system_prompt, mt)
    if result:
        return result

    raise RuntimeError(
        "All LLM providers failed. Check AWS/OpenAI credentials in .env"
    )


def invoke_llm_json(
    messages: List[Dict],
    system_prompt: str = "",
    max_tokens: Optional[int] = None,
) -> dict:
    """Call LLM and parse JSON response. Returns dict or raises."""
    # Append JSON instruction to system prompt
    json_system = (
        system_prompt
        + "\n\nIMPORTANT: Respond ONLY with valid JSON. No markdown, no backticks, no explanation."
    )
    raw = invoke_llm(messages, json_system, max_tokens, temperature=0.1)
    # Strip accidental markdown fences
    clean = raw.strip().strip("```json").strip("```").strip()
    try:
        return json.loads(clean)
    except json.JSONDecodeError as exc:
        logger.error("LLM returned non-JSON: %s\nRaw: %s", exc, raw[:300])
        raise ValueError(f"LLM did not return valid JSON: {exc}") from exc
