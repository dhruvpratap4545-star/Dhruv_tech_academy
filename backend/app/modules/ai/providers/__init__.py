"""Provider adapters. Each turns one prompt into text and a token count; nothing else.

Plain REST over ``httpx`` rather than vendor SDKs: one small dependency the tests already
use, no transitive packages to audit, and the request that leaves the platform is visible
in one place. Adding a provider is one class here and one entry in ``get_provider``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


class ProviderError(Exception):
    """The call failed — timeout, refusal, outage, missing key. The gateway may retry on
    the fallback model. The message is for logs only and never shown to a user."""


@dataclass(slots=True, frozen=True)
class Attachment:
    """A file sent alongside the prompt — a syllabus PDF, a photo of a page. Only types the
    upload validator accepts (PDF, JPEG, PNG) ever reach a provider."""

    content_type: str
    data: bytes


@dataclass(slots=True)
class ProviderRequest:
    model_id: str
    system_prompt: str
    user_text: str
    max_output_tokens: int
    safety_level: str = "standard"
    attachments: tuple[Attachment, ...] = ()
    #: A JSON Schema the answer must follow. Providers that support structured output
    #: enforce it; the others are told in the prompt, and the caller validates either way.
    json_schema: dict | None = None
    #: Overrides ``AI_REQUEST_TIMEOUT_SECONDS`` for a call known to be slow (a long document).
    timeout_seconds: float | None = None


@dataclass(slots=True)
class ProviderResult:
    text: str
    input_tokens: int
    output_tokens: int
    #: True when the provider's own safety filter withheld the answer.
    safety_blocked: bool = False


class AiProvider(ABC):
    name: str

    @abstractmethod
    def configured(self) -> bool: ...

    @abstractmethod
    async def complete(self, request: ProviderRequest) -> ProviderResult: ...


def get_provider(name: str) -> AiProvider:
    from app.core.config import settings
    from app.modules.ai.providers.anthropic import AnthropicProvider
    from app.modules.ai.providers.fake import FakeProvider
    from app.modules.ai.providers.gemini import GeminiProvider

    # Fake mode answers everything locally, whatever model was configured, so local
    # development and tests never reach a real provider or spend money.
    if settings.use_fake_ai or name == "fake":
        return FakeProvider()
    if name == "gemini":
        return GeminiProvider()
    if name == "anthropic":
        return AnthropicProvider()
    raise ProviderError(f"unknown provider {name!r}")


PROVIDER_NAMES = ("gemini", "anthropic", "fake")
