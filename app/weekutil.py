"""ISO year+week helpers.

Everywhere in this app, `week` is an ISO week (1-53) and `year` is the
corresponding ISO year (which may differ from the calendar year for
dates in early January or late December).
"""

from datetime import date, timedelta


def current_iso_year_week() -> tuple[int, int]:
    y, w, _ = date.today().isocalendar()
    return y, w


def iso_week_dates(year: int, week: int) -> list[date]:
    """Return the 7 dates (Monday..Sunday) of the given ISO year+week."""
    monday = date.fromisocalendar(year, week, 1)
    return [monday + timedelta(days=i) for i in range(7)]


def shift_iso_week(year: int, week: int, weeks: int) -> tuple[int, int]:
    """Return the (year, week) that is `weeks` ISO weeks away from (year, week)."""
    monday = date.fromisocalendar(year, week, 1)
    shifted = monday + timedelta(days=7 * weeks)
    y, w, _ = shifted.isocalendar()
    return y, w


def week_delta(year: int, week: int, today: date | None = None) -> int:
    """Signed distance in ISO weeks from the current week (0 = this week,
    positive = future, negative = past). Uses Monday-to-Monday day difference
    to avoid off-by-one at ISO year boundaries."""
    if today is None:
        today = date.today()
    target_monday = date.fromisocalendar(year, week, 1)
    y, w, _ = today.isocalendar()
    current_monday = date.fromisocalendar(y, w, 1)
    return (target_monday - current_monday).days // 7


def week_relative_label(delta: int) -> str:
    """Italian relative-week label for the header (SPEC.md §4.4)."""
    if delta == 0:
        return "Questa settimana"
    if delta == 1:
        return "Prossima settimana"
    if delta == -1:
        return "Settimana scorsa"
    if delta > 1:
        return f"Tra {delta} settimane"
    return f"{-delta} settimane fa"
