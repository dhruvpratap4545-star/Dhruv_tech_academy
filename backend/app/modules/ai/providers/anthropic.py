"""Anthropic Claude over the Messages API. Optional second provider, used as a fallback
when ``ANTHROPIC_API_KEY`` is configured."""

from __future__ import annotations

import httpx

from app.core.config import settings
from app.modules.ai.providers import AiProvider, ProviderError, ProviderRequest, ProviderResult

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


class AnthropicProvider(AiProvider):
    name = "anthropic"

    def configured(self) -> bool:
        return bool(settings.anthropic_api_key.get_secret_value())

    async def complete(self, request: ProviderRequest) -> ProviderResult:
        if not self.configured():
            raise ProviderError("ANTHROPIC_API_KEY is not configured")
        body = {
            "model": request.model_id,
            "max_tokens": request.max_output_tokens,
            "system": request.system_prompt,
            "messages": [{"role": "user", "content": request.user_text}],
        }
        try:
            async with httpx.AsyncClient(timeout=settings.ai_request_timeout_seconds) as client:
                response = await client.post(
                    URL,
                    json=body,
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
