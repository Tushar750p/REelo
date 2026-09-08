"""Unit tests for opaque feed cursor pagination."""
import pytest

from feed_pagination import cursor_predicate, decode_cursor, encode_cursor


def test_cursor_round_trip():
    cursor = encode_cursor("2026-09-08T10:20:30+00:00", "video-123")
    assert decode_cursor(cursor) == ("2026-09-08T10:20:30+00:00", "video-123")


def test_cursor_predicate_is_keyset_and_parameterized():
    cursor = encode_cursor("2026-09-08T10:20:30+00:00", "video-123")
    sql, params = cursor_predicate(cursor)
    assert "v.created_at < ?" in sql
    assert "v.created_at = ?" in sql
    assert "v.id < ?" in sql
    assert params == (
        "2026-09-08T10:20:30+00:00",
        "2026-09-08T10:20:30+00:00",
        "video-123",
    )


def test_empty_cursor_is_first_page():
    assert cursor_predicate(None) == ("", ())


@pytest.mark.parametrize("cursor", ["bad", "!@#$", "e30", "a" * 513])
def test_invalid_cursor_rejected(cursor):
    with pytest.raises(ValueError):
        decode_cursor(cursor)
