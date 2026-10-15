"""Email bodies.

Plain inline-styled HTML with a text fallback. No template engine and no external images:
Gmail and Outlook strip most CSS, images are blocked by default, and an OTP email that
renders as an empty box is a support call.

Copy is simple Indian English, matching the UI.
"""

from __future__ import annotations

from app.core.config import settings
from app.modules.notifications.email import EmailMessage

_BRAND = "Dhruv Online Academy"


def _wrap(heading: str, body_html: str) -> str:
    return f"""\
<div style="font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;
            max-width:520px;margin:0 auto;padding:24px;color:#0f172a;">
  <h1 style="font-size:18px;margin:0 0 16px;">{_BRAND}</h1>
  <h2 style="font-size:16px;font-weight:600;margin:0 0 12px;">{heading}</h2>
  {body_html}
  <p style="font-size:12px;color:#64748b;margin-top:28px;">
    This is an automated message. Please do not reply to it.
  </p>
</div>"""


def _button(href: str, label: str) -> str:
    """A link styled as a button, with the URL spelled out underneath.

    Both, deliberately. Mail clients and corporate gateways rewrite or strip anchors often
    enough that a button alone is a dead end, and a recipient who can see the address can
    still type it. The plain-text part of every message carries the same URL.
    """
    return (
        f'<p style="margin:20px 0;"><a href="{href}" '
        f'style="display:inline-block;background:#1e3a5f;color:#ffffff;text-decoration:none;'
        f'padding:12px 22px;border-radius:8px;font-weight:600;font-size:15px;">{label}</a></p>'
        f'<p style="font-size:12px;color:#64748b;margin:0;">'
        f'Or open this address: <span style="color:#1e3a5f;">{href}</span></p>'
    )


def _link(path: str, email: str) -> str:
    """A link to one of the app's pages, with the address pre-filled.

    Pre-filling the email saves the recipient retyping the address the message was just
    sent to. It is not a credential and grants nothing on its own — the six-digit code is
    what authorises the change, and it is deliberately not in the URL, where it would end
    up in browser history, proxy logs and anything that rewrites links.
    """
    from urllib.parse import quote

    return f"{settings.frontend_url.rstrip('/')}{path}?email={quote(email)}"


def _code_block(code: str) -> str:
    return (
        f'<p style="font-size:28px;letter-spacing:6px;font-weight:700;'
        f"margin:16px 0;padding:12px 16px;background:#f1f5f9;border-radius:8px;"
        f'text-align:center;">{code}</p>'
    )


def password_reset(to: str, full_name: str, code: str) -> EmailMessage:
    minutes = settings.otp_reset_ttl_minutes
    return EmailMessage(
        to=to,
        subject=f"Your {_BRAND} password reset code",
        html=_wrap(
            f"Hello {full_name},",
            f"<p>Use this code to reset your password. It is valid for {minutes} minutes "
            f"and can be used once.</p>{_code_block(code)}"
            f"{_button(_link('/forgot-password', to), 'Enter your code')}"
            "<p>If you did not ask for this, you can ignore this email. "
            "Your password has not changed.</p>",
        ),
        text=(
            f"Hello {full_name},\n\n"
            f"Your {_BRAND} password reset code is {code}.\n"
            f"It is valid for {minutes} minutes and can be used once.\n\n"
            f"Enter it here: {_link('/forgot-password', to)}\n\n"
            "If you did not ask for this, you can ignore this email."
        ),
    )


def password_setup(
    to: str, full_name: str, code: str, invited_by: str | None = None
) -> EmailMessage:
    hours = settings.otp_setup_ttl_hours
    who = f" by {invited_by}" if invited_by else ""
    return EmailMessage(
        to=to,
        subject=f"Set your {_BRAND} password",
        html=_wrap(
            f"Welcome, {full_name}",
            f"<p>You have been added to {_BRAND}{who}. Use this code to set your "
            f"password. It is valid for {hours} hours.</p>{_code_block(code)}"
            f"{_button(_link('/set-password', to), 'Set your password')}"
            "<p>Once your password is set you can log in with your email address.</p>",
        ),
        text=(
            f"Welcome, {full_name}\n\n"
            f"You have been added to {_BRAND}{who}.\n"
            f"Your setup code is {code}. It is valid for {hours} hours.\n\n"
            f"Set your password here: {_link('/set-password', to)}\n\n"
            "Once your password is set you can log in with your email address."
        ),
    )


def password_changed(to: str, full_name: str) -> EmailMessage:
    """Sent after every password change or reset (PRD §7.3). This is a security signal: it
    is how someone finds out their account was taken over."""
    return EmailMessage(
        to=to,
        subject=f"Your {_BRAND} password was changed",
        html=_wrap(
            f"Hello {full_name},",
            "<p>Your password was changed just now, and you have been logged out on all "
            "other devices.</p>"
            "<p><strong>If this was not you, reset your password immediately and tell "
            "your administrator.</strong></p>",
        ),
        text=(
            f"Hello {full_name},\n\n"
            "Your password was changed just now, and you have been logged out on all "
            "other devices.\n\n"
            "If this was not you, reset your password immediately and tell your "
            "administrator."
        ),
    )
