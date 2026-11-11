"""Google Gemini over the REST ``generateContent`` API.

Tokens come from the response's ``usageMetadata``. Thinking tokens are billed as output, so
they are added to the output count — leaving them out would under-report cost on every
thinking model.

The API key travels in the ``x-goog-api-key`` header, never the URL, so it cannot end up in
an access log or an error message that quotes the URL.
"""

from __future__ import annotations

import base64

import httpx

from app.core.config import settings
from app.modules.ai.providers import AiProvider, ProviderError, ProviderRequest, ProviderResult

BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
_CATEGORIES = (
    "HARM_CATEGORY_HARASSMENT",
    "HARM_CATEGORY_HATE_SPEECH",
    "HARM_CATEGORY_SEXUALLY_EXPLICIT",
    "HARM_CATEGORY_DANGEROUS_CONTENT",
)
SAFETY_MESSAGE = "I can't help with that. Please ask your teacher, or try a different question."


def safety_settings(level: str) -> list[dict[str, str]]:
    """The strictest threshold for the kids level; block medium-and-above otherwise."""
    threshold = "BLOCK_LOW_AND_ABOVE" if level == "kids" else "BLOCK_MEDIUM_AND_ABOVE"
    return [{"category": c, "threshold": threshold} for c in _CATEGORIES]


def build_body(request: ProviderRequest) -> dict:
    # Files first, then the instruction: Gemini reads a document more reliably when the
    # question about it comes after it.
    parts: list[dict] = [
        {
            "inline_data": {
                "mime_type": attachment.content_type,
                "data": base64.b64encode(attachment.data).decode("ascii"),
            }
        }
        for attachment in request.attachments
    ]
    parts.append({"text": request.user_text})
    generation: dict = {"maxOutputTokens": request.max_output_tokens}
    if request.json_schema is not None:
        generation["responseMimeType"] = "application/json"
        generation["responseJsonSchema"] = request.json_schema
    return {
        "systemInstruction": {"parts": [{"text": request.system_prompt}]},
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": generation,
        "safetySettings": safety_settings(request.safety_level),
    }


def parse_response(data: dict) -> ProviderResult:
    usage = data.get("usageMetadata") or {}
    input_tokens = int(usage.get("promptTokenCount") or 0)
    output_tokens = int(usage.get("candidatesTokenCount") or 0) + int(
        usage.get("thoughtsTokenCount") or 0
    )
    if (data.get("promptFeedback") or {}).get("blockReason"):
        return ProviderResult(SAFETY_MESSAGE, input_tokens, output_tokens, safety_blocked=True)

    candidates = data.get("candidates") or []
    if not candidates:
        raise ProviderError("gemini returned no candidates")
    candidate = candidates[0]
    if candidate.get("finishReason") in ("SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII"):
        return ProviderResult(SAFETY_MESSAGE, input_tokens, output_tokens, safety_blocked=True)
    parts = (candidate.get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
    if not text.strip():
        raise ProviderError(
            f"gemini returned no text (finishReason={candidate.get('finishReason')})"
        )
    return ProviderResult(text, input_tokens, output_tokens)


class GeminiProvider(AiProvider):
    name = "gemini"

    def configured(self) -> bool:
        return bool(settings.gemini_api_key.get_secret_value())

    async def complete(self, request: ProviderRequest) -> ProviderResult:
        if not self.configured():
            raise ProviderError("GEMINI_API_KEY is not configured")
        url = f"{BASE_URL}/models/{request.model_id}:generateContent"
        try:
            timeout = request.timeout_seconds or settings.ai_request_timeout_seconds
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    url,
                    json=build_body(request),
                    headers={"x-goog-api-key": settings.gemini_api_key.get_secret_value()},
                )
        except httpx.HTTPError as exc:
            raise ProviderError(f"gemini request failed: {type(exc).__name__}") from exc
        if response.status_code != 200:
            # Status only: the body can echo the prompt back.
            raise ProviderError(f"gemini returned HTTP {response.status_code}")
        return parse_response(response.json())
