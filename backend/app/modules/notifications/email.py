"""Email sending, behind one interface (PRD §10.5).

Everything goes through ``send_email``. Resend is today's provider; swapping to SES later
means adding a class here and changing nothing else. Tests get the in-memory provider, so
no test can ever reach a real inbox.

Delivery is intentionally best-effort and never blocks a response: OTP endpoints hand the
send to FastAPI's background tasks. A provider outage must not stop a password reset being
recorded — the user can request a new code.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class EmailMessage:
    to: str
    subject: str
    html: str
    text: str


class EmailProvider(ABC):
    @abstractmethod
    async def send(self, message: EmailMessage) -> None: ...


class ConsoleEmailProvider(EmailProvider):
    """Used whenever no Resend key is configured.

    In **local** development it prints the whole message, because otherwise the OTP exists
    nowhere a developer can reach — it is hashed in the database and never returned by the
    API, so the forgot-password and invitation flows would be impossible to exercise.

    Anywhere else, only the recipient and subject are logged. Reaching this provider in
    staging or production means ``RESEND_API_KEY`` is missing, and that misconfiguration
    must not turn the log file into a list of live one-time codes.
    """

    async def send(self, message: EmailMessage) -> None:
        if settings.environment == "local":
            logger.info(
                "email not sent (no RESEND_API_KEY) - body below for local testing",
                extra={"to": message.to, "subject": message.subject, "body": message.text},
            )
        else:
            logger.warning(
                "email not sent: RESEND_API_KEY is not configured",
                extra={"to": message.to, "subject": message.subject},
            )


@dataclass(slots=True)
class MemoryEmailProvider(EmailProvider):
    """Test double. Captures messages so tests can assert on what was sent."""

    outbox: list[EmailMessage] = field(default_factory=list)

    async def send(self, message: EmailMessage) -> None:
        self.outbox.append(message)

    def last_to(self, address: str) -> EmailMessage | None:
        target = address.lower()
        return next((m for m in reversed(self.outbox) if m.to.lower() == target), None)

    def clear(self) -> None:
        self.outbox.clear()


class ResendEmailProvider(EmailProvider):
    """Production. Imported lazily so the dependency is not required to run tests."""

    async def send(self, message: EmailMessage) -> None:
        import anyio
        import resend

        resend.api_key = settings.resend_api_key.get_secret_value()
        payload = {
            "from": settings.email_from,
            "to": [message.to],
            "subject": message.subject,
            "html": message.html,
            "text": message.text,
        }
        # The SDK is synchronous; run it off the event loop so one slow call cannot
        # stall every other request this worker is serving.
        await anyio.to_thread.run_sync(lambda: resend.Emails.send(payload))


def _default_provider() -> EmailProvider:
    if settings.environment == "test":
        return MemoryEmailProvider()
    if settings.resend_api_key.get_secret_value():
        return ResendEmailProvider()
    logger.warning("no RESEND_API_KEY set; emails will be logged and not delivered")
    return ConsoleEmailProvider()


_provider: EmailProvider = _default_provider()


def get_provider() -> EmailProvider:
    return _provider


def set_provider(provider: EmailProvider) -> None:
    """Used by tests and by local tooling. Not reachable from any HTTP route."""
    global _provider
    _provider = provider


async def send_email(message: EmailMessage) -> None:
    """Never raises. A failed send is logged and swallowed, because it reaches the caller
    through a background task where an exception would only produce a stack trace nobody
    sees — and the user-visible flows are designed to tolerate a missing email."""
    try:
        await _provider.send(message)
    except Exception:
        logger.exception("email send failed", extra={"to": message.to})
