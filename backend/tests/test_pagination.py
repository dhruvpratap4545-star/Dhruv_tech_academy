"""Keyset cursors (PRD §8 pagination)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from app.core.errors import ValidationFailed
from app.core.pagination import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    clamp_limit,
    decode_cursor,
    encode_cursor,
    split_page,
)

NOW = datetime(2026, 10, 7, 12, 30, tzinfo=UTC)
ROW_ID = uuid.uuid4()


def test_cursor_round_trips() -> None:
    when, which = decode_cursor(encode_cursor(NOW, ROW_ID))
    assert when == NOW
    assert which == ROW_ID


def test_cursor_is_opaque() -> None:
    """Callers must not be able to read or build one, so we stay free to change the key."""
    cursor = encode_cursor(NOW, ROW_ID)
    assert str(ROW_ID) not in cursor
    assert "2026" not in cursor


def test_cursor_is_url_safe() -> None:
    cursor = encode_cursor(NOW, ROW_ID)
    assert "+" not in cursor and "/" not in cursor and "=" not in cursor


@pytest.mark.parametrize("bad", ["", "!!!!", "YWJj", "e30", "bm90LWpzb24=", "x" * 500])
def test_a_tampered_cursor_is_rejected_cleanly(bad: str) -> None:
    """Attacker-controlled input: it must raise a domain error, never a 500."""
    with pytest.raises(ValidationFailed):
        decode_cursor(bad)


def test_a_rejected_cursor_is_not_echoed_back() -> None:
    try:
        decode_cursor("<script>alert(1)</script>")
    except ValidationFailed as exc:
        assert "script" not in exc.message


def test_limit_defaults_and_clamps() -> None:
    assert clamp_limit(None) == DEFAULT_LIMIT
    assert clamp_limit(5) == 5
    assert clamp_limit(10_000) == MAX_LIMIT


def test_a_non_positive_limit_is_rejected() -> None:
    with pytest.raises(ValidationFailed):
        clamp_limit(0)


class Row:
    def __init__(self, created_at: datetime, row_id: uuid.UUID) -> None:
        self.created_at = created_at
        self.id = row_id


def test_a_full_page_yields_a_next_cursor() -> None:
    """One extra row is fetched as a sentinel, so no COUNT query is ever needed."""
    rows = [Row(NOW, uuid.uuid4()) for _ in range(4)]
    page, cursor = split_page(rows, limit=3)
    assert len(page) == 3
    assert cursor is not None


def test_a_short_page_is_the_last_page() -> None:
    page, cursor = split_page([Row(NOW, uuid.uuid4()) for _ in range(2)], limit=3)
    assert len(page) == 2
    assert cursor is None


def test_an_empty_page_is_the_last_page() -> None:
    page, cursor = split_page([], limit=3)
    assert page == []
    assert cursor is None


def test_the_cursor_points_at_the_last_returned_row() -> None:
    rows = [Row(NOW, uuid.uuid4()) for _ in range(4)]
    page, cursor = split_page(rows, limit=3)
    assert decode_cursor(cursor)[1] == page[-1].id
