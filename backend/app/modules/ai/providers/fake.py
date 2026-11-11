"""Deterministic stand-in for local development and tests. Never calls out."""

from __future__ import annotations

from app.modules.ai.providers import AiProvider, ProviderError, ProviderRequest, ProviderResult

#: A prompt containing this fails, so tests can exercise the fallback path.
FAIL_MARKER = "__fail__"
#: Fails only on the named model, so a fallback to a different model succeeds.
FAIL_PRIMARY_MARKER = "__fail_primary__"
#: What Gemini charges for one image or PDF page, near enough for tests.
ATTACHMENT_TOKENS = 258


def count_tokens(text: str) -> int:
    """Roughly four characters a token, as real tokenisers average for English."""
    return max(1, len(text) // 4)


class FakeProvider(AiProvider):
    name = "fake"

    def configured(self) -> bool:
        return True

    async def complete(self, request: ProviderRequest) -> ProviderResult:
        if FAIL_MARKER in request.user_text:
            raise ProviderError("fake provider asked to fail")
        if FAIL_PRIMARY_MARKER in request.user_text and not request.model_id.endswith("-lite"):
            raise ProviderError("fake provider asked to fail the primary model")
        text = f"[fake:{request.model_id}] {request.user_text[-200:]}"[
            : request.max_output_tokens * 4
        ]
        return ProviderResult(
            text=text,
            input_tokens=count_tokens(request.system_prompt)
            + count_tokens(request.user_text)
            + ATTACHMENT_TOKENS * len(request.attachments),
            output_tokens=count_tokens(text),
        )
