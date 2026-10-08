"""Application settings.

Every environment variable the backend reads is declared here. Modules import
``settings`` from this file; they never touch ``os.environ`` directly.
Add a placeholder to ``backend/.env.example`` whenever a new variable is added.
"""

import re
from functools import lru_cache
from typing import Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["local", "test", "staging", "production"]


ESCAPED_NEWLINE = "\\n"
_PEM_BLOCK = re.compile(r"-----BEGIN ([A-Z0-9 ]+)-----(.*?)-----END \1-----", re.DOTALL)


def _normalise_pem(value: str | None) -> str:
    """Accept a PEM whose line breaks arrived as the two characters backslash-n.

    Most secret stores — Render's dashboard included — hand environment variables back as a
    single line, so a pasted key often arrives escaped. Without this the key loads as one
    malformed line and the failure surfaces as a 500 on the first login rather than
    anywhere useful. Keys with real newlines pass through untouched.
    """
    if not value:
        return ""
    value = value.replace(ESCAPED_NEWLINE, "\n").strip().strip("\"'").strip()
    # A paste into a single-line field can also turn the line breaks into spaces, which
    # corrupts the base64 ("Invalid padding"). Rebuild the canonical framing: header, body
    # with every whitespace removed and wrapped at 64 columns, footer.
    match = _PEM_BLOCK.fullmatch(value)
    if not match:
        return value
    label, body = match.group(1), re.sub(r"\s+", "", match.group(2))
    lines = [body[i : i + 64] for i in range(0, len(body), 64)]
    return "\n".join([f"-----BEGIN {label}-----", *lines, f"-----END {label}-----"])


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: Environment = "local"
    app_name: str = "Dhruv Online Academy API"
    api_v1_prefix: str = "/api/v1"

    # Database
    database_url: str = "postgresql+asyncpg://app:app@localhost:5432/app"
    test_database_url: str | None = None
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_pool_recycle_seconds: int = 1800
    db_echo: bool = False

    # Tokens (PRD §7.2) — ES256 PEM key pair, rotated via jwt_key_id
    jwt_private_key: SecretStr = SecretStr("")
    jwt_public_key: str = ""
    jwt_key_id: str = "k1"
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 7
    refresh_token_ttl_days_remembered: int = 30

    # Authorization cache (PRD §5.2, §7.2 "role cache <= 60 s")
    permission_cache_ttl_seconds: int = 60
    permission_cache_max_entries: int = 5_000

    # OTP (PRD §7.3)
    otp_pepper: SecretStr = SecretStr("")
    otp_length: int = 6
    otp_reset_ttl_minutes: int = 10
    otp_setup_ttl_hours: int = 48
    otp_max_attempts: int = 5
    otp_resend_cooldown_seconds: int = 60

    # Login protection (PRD §7.4)
    max_failed_logins: int = 5
    account_lock_minutes: int = 15

    # Rate limits (PRD §7.4). Values are slowapi strings so they are tunable per environment.
    rate_limit_login: str = "20/minute"
    rate_limit_forgot_password: str = "10/hour"
    rate_limit_verify_otp: str = "20/hour"
    rate_limit_register: str = "5/hour"
    rate_limit_default: str = "300/minute"
    rate_limits_enabled: bool = True

    # Product flags
    # PRD §14 Q2 is still open: this lets self sign-up be switched off at launch without
    # a code change.
    direct_signup_enabled: bool = True
    consent_version: str = "2026-10-01"

    # Email (PRD §9)
    resend_api_key: SecretStr = SecretStr("")
    email_from: str = "Dhruv Online Academy <noreply@dhruvonlineacademy.com>"

    # Where the web app lives, used to build links in emails. An OTP with no way to reach
    # the page that accepts it leaves the recipient holding six digits and no door.
    frontend_url: str = "http://localhost:5173"

    # Web security (PRD §7.5)
    cookie_domain: str | None = None
    cors_origins: list[str] = []

    # Built frontend (frontend/dist). When set, the API also serves the web app, so the
    # whole platform runs on one URL. Unset locally, where Vite serves the frontend.
    frontend_dist_dir: str | None = None

    # Seed + monitoring
    seed_superadmin_email: str | None = None
    sentry_dsn: str | None = None

    @field_validator("jwt_public_key", mode="before")
    @classmethod
    def _unescape_public_key(cls, value: str) -> str:
        return _normalise_pem(value)

    @field_validator("jwt_private_key", mode="before")
    @classmethod
    def _unescape_private_key(cls, value: str | SecretStr) -> str:
        raw = value.get_secret_value() if isinstance(value, SecretStr) else value
        return _normalise_pem(raw)

    @field_validator("database_url", "test_database_url")
    @classmethod
    def _use_async_driver(cls, value: str | None) -> str | None:
        """Render supplies ``postgres://…``; SQLAlchemy async needs ``postgresql+asyncpg://…``."""
        if not value:
            return value
        if value.startswith("postgres://"):
            return value.replace("postgres://", "postgresql+asyncpg://", 1)
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+asyncpg://", 1)
        return value

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def cookie_secure(self) -> bool:
        """Cookies are only marked Secure where the site is served over https."""
        return self.environment in ("staging", "production")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
