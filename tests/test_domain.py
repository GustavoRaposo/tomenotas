"""Tests for tomenotas.domain — pure rules."""

from datetime import datetime

from tomenotas.domain.note import preview
from tomenotas.domain.period import period_since


def test_preview_truncates_at_60_chars():
    assert preview("a" * 100) == "a" * 60
    assert preview("curta") == "curta"


def test_preview_is_always_a_single_line():
    # newlines and repeated whitespace become a single space — note list
    # items must keep a uniform height
    assert preview("linha um\nlinha dois\n\nlinha três") == (
        "linha um linha dois linha três"
    )
    assert preview("  espaços \t e \n quebras  ") == "espaços e quebras"
    assert len(preview(("palavra\n" * 30))) == 60


def test_period_since_translates_the_ui_shortcuts():
    now = datetime(2026, 7, 23, 14, 30, 45)
    assert period_since("today", now) == "2026-07-23T00:00:00"
    assert period_since("7days", now) == "2026-07-16T14:30:45"
    assert period_since("30days", now) == "2026-06-23T14:30:45"
    assert period_since("", now) is None
    assert period_since("anything-else", now) is None


def test_period_since_without_clock_uses_now():
    assert period_since("today").endswith("T00:00:00")
