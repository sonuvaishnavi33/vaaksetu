
import json
import logging
from typing import Optional
import boto3
from botocore.exceptions import BotoCoreError, ClientError
from backend.config import settings

logger = logging.getLogger(__name__)


def _build_client():
    """Build a Bedrock runtime client. Returns None if AWS is not configured."""
    if not settings.is_aws_configured():
        logger.warning(
            "AWS credentials not configured. "
            "Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY in .env"
        )
        return None
    try:
        client = boto3.client(
            service_name="bedrock-runtime",
            region_name=settings.aws_region,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
        )
        logger.info("Bedrock client initialised (region=%s)", settings.aws_region)
        return client
    except Exception as exc:
        logger.error("Failed to initialise Bedrock client: %s", exc)
        return None


# Module-level singleton — created once, reused throughout.
_bedrock_client = None


def get_bedrock_client():
    global _bedrock_client
    if _bedrock_client is None:
        _bedrock_client = _build_client()
    return _bedrock_client


def invoke_bedrock(
    messages: list[dict],
    system_prompt: str = "",
    max_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
) -> Optional[str]:
    """
    Call Claude via AWS Bedrock Messages API.

    Args:
        messages: List of {"role": "user"/"assistant", "content": str}
        system_prompt: Optional system instructions
        max_tokens: Override default from settings
        temperature: Override default from settings

    Returns:
        Text response string, or None on failure.
    """
    client = get_bedrock_client()
    if client is None:
        return None

    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens or settings.bedrock_max_tokens,
        "temperature": temperature or settings.bedrock_temperature,
        "messages": messages,
    }
    if system_prompt:
        body["system"] = system_prompt

    try:
        response = client.invoke_model(
            modelId=settings.bedrock_model_id,
            body=json.dumps(body),
            contentType="application/json",
            accept="application/json",
        )
        result = json.loads(response["body"].read())
        return result["content"][0]["text"]
    except (BotoCoreError, ClientError) as exc:
        logger.error("Bedrock invocation error: %s", exc)
        return None
    except Exception as exc:
        logger.error("Unexpected Bedrock error: %s", exc)
        return None
