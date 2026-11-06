"""Cost and calendar arithmetic for the AI Control Room. Pure functions, no I/O.

Days and months are Indian ones. A student's "30 requests a day" resets at midnight IST,
not at 05:30 IST when UTC turns over, and a budget month runs from the 1st in India.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Final

IST: Final = timezone(timedelta(hours=5, minutes=30))
_MILLION: Final = Decimal(1_000_000)


def cost_paise(
    input_tokens: int,
    output_tokens: int,
    *,
    input_price_per_mtok_usd: float,
    output_price_per_mtok_usd: float,
    usd_to_inr: float,
) -> int:
    """``(in × in_price + out × out_price) / 1e6 × usd_to_inr``, in whole paise.

    Decimal throughout, built from the *string* of each float, so ``0.1`` is a tenth and not
    ``0.1000000000000000055…``. Rounded half-up once, at the end: rounding each request
    down would make a million tiny requests cost nothing.
    """
    usd = (
        Decimal(input_tokens) * Decimal(str(input_price_per_mtok_usd))
        + Decimal(output_tokens) * Decimal(str(output_price_per_mtok_usd))
    ) / _MILLION
    paise = usd * Decimal(str(usd_to_inr)) * 100
    return int(paise.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def month_key(now: datetime) -> str:
    """``"2026-11"`` for any moment in November in India."""
    return now.astimezone(IST).strftime("%Y-%m")


def previous_month_key(month: str) -> str:
    year, number = (int(part) for part in month.split("-"))
    return f"{year - 1}-12" if number == 1 else f"{year}-{number - 1:02d}"


def start_of_ist_day(now: datetime) -> datetime:
    """Midnight IST on the day ``now`` falls on, as an aware datetime."""
    return datetime.combine(now.astimezone(IST).date(), time.min, tzinfo=IST)


def percent_used(used: int, limit: int | None) -> float | None:
    if not limit:
        return None
    return used * 100 / limit


def fullest(
    used_paise: int, limit_paise: int | None, used_tokens: int, limit_tokens: int | None
) -> tuple[int, int | None]:
    """The (used, limit) pair nearer its cap. A budget with both a rupee and a token limit
    blocks on whichever runs out first, so its percentage and alerts must follow that one."""
    pairs = [(used_paise, limit_paise), (used_tokens, limit_tokens)]
    return max(pairs, key=lambda pair: percent_used(*pair) or 0)


def crossed_thresholds(
    used: int, limit: int | None, thresholds: list[int], already_sent: list[int]
) -> list[int]:
    """Thresholds reached and not yet alerted, lowest first."""
    percent = percent_used(used, limit)
    if percent is None:
        return []
    return sorted(t for t in thresholds if percent >= t and t not in already_sent)


def format_inr(paise: int) -> str:
    """``₹1,23,456.78`` — Indian digit grouping, as the client reads money."""
    rupees, rest = divmod(abs(paise), 100)
    digits = str(rupees)
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        digits = ",".join([*groups, tail])
    sign = "-" if paise < 0 else ""
    return f"{sign}₹{digits}.{rest:02d}"
