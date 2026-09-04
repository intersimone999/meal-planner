"""Tests for the ISO-week helpers, focused on the relative-label logic."""

from datetime import date

from app.weekutil import week_delta, week_relative_label


def test_week_delta_zero_this_week():
    today = date(2026, 9, 4)  # Fri
    y, w, _ = today.isocalendar()
    assert week_delta(y, w, today=today) == 0


def test_week_delta_adjacent():
    today = date(2026, 9, 4)
    y, w, _ = today.isocalendar()
    assert week_delta(y, w + 1, today=today) == 1
    assert week_delta(y, w - 1, today=today) == -1


def test_week_delta_crosses_year_boundary():
    # Today is Mon Jan 4 2027 (ISO week 1, 2027). Year 2026 has 53 ISO weeks,
    # so week 51 of 2026 is three weeks before week 1 of 2027:
    #   -1 → week 53/2026, -2 → week 52/2026, -3 → week 51/2026.
    today = date(2027, 1, 4)
    assert week_delta(2026, 51, today=today) == -3
    assert week_delta(2026, 53, today=today) == -1
    # And forward across the boundary:
    today2 = date(2026, 12, 28)  # Mon of ISO week 53, 2026
    assert week_delta(2027, 1, today=today2) == 1


def test_relative_label():
    assert week_relative_label(0) == "Questa settimana"
    assert week_relative_label(1) == "Prossima settimana"
    assert week_relative_label(-1) == "Settimana scorsa"
    assert week_relative_label(2) == "Tra 2 settimane"
    assert week_relative_label(5) == "Tra 5 settimane"
    assert week_relative_label(-2) == "2 settimane fa"
    assert week_relative_label(-10) == "10 settimane fa"
