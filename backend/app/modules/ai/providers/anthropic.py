"""Anthropic Claude over the Messages API. Optional second provider, used as a fallback
when ``ANTHROPIC_API_KEY`` is configured."""

from __future__ import annotations

import base64
import json

import httpx

from app.core.config import settings
from app.modules.ai.providers import (
    AiProvider,
    Attachment,
    ProviderError,
    ProviderRequest,
    ProviderResult,
)

URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"


def parse_response(data: dict) -> ProviderResult:
    usage = data.get("usage") or {}
    text = "".join(b.get("text", "") for b in data.get("content") or [] if b.get("type") == "text")
    if data.get("stop_reason") == "refusal":
        from app.modules.ai.providers.gemini import SAFETY_MESSAGE

        return ProviderResult(
            SAFETY_MESSAGE,
            int(usage.get("input_tokens") or 0),
            int(usage.get("output_tokens") or 0),
            safety_blocked=True,
        )
    if not text.strip():
        raise ProviderError("anthropic returned no text")
    return ProviderResult(
        text, int(usage.get("input_tokens") or 0), int(usage.get("output_tokens") or 0)
    )


def _block(attachment: Attachment) -> dict:
    kind = "document" if attachment.content_type == "application/pdf" else "image"
    return {
        "type": kind,
        "source": {
            "type": "base64",
            "media_type": attachment.content_type,
            "data": base64.b64encode(attachment.data).decode("ascii"),
        },
    }


def build_body(request: ProviderRequest) -> dict:
    text = request.user_text
    if request.json_schema is not None:
        # No schema enforcement here: say it in the prompt, and the caller validates.
        text += "\n\nReply with JSON only, matching this JSON Schema:\n" + json.dumps(
            request.json_schema, separators=(",", ":")
        )
    content: list[dict] | str = text
    if request.attachments:
        content = [*(_block(a) for a in request.attachments), {"type": "text", "text": text}]
    return {
        "model": request.model_id,
        "max_tokens": request.max_output_tokens,
        "system": request.system_prompt,
        "messages": [{"role": "user", "content": content}],
    }


class AnthropicProvider(AiProvider):
    name = "anthropic"

    def configured(self) -> bool:
        return bool(settings.anthropic_api_key.get_secret_value())

    async def complete(self, request: ProviderRequest) -> ProviderResult:
        if not self.configured():
            raise ProviderError("ANTHROPIC_API_KEY is not configured")
        try:
            timeout = request.timeout_seconds or settings.ai_request_timeout_seconds
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    URL,
                    json=build_body(request),
                    headers={
                        "x-api-key": settings.anthropic_api_key.get_secret_value(),
                        "anthropic-version": API_VERSION,
                    },
                )
        except httpx.HTTPError as exc:
            raise ProviderError(f"anthropic request failed: {type(exc).__name__}") from exc
        if response.status_code != 200:
            raise ProviderError(f"anthropic returned HTTP {response.status_code}")
        return parse_response(response.json())
