"""Italian labels for user-facing text derived from data (day/slot/month names)."""

from datetime import date

SLOTS: list[str] = ["lunch", "dinner"]

SLOT_LABELS: dict[str, str] = {
    "lunch": "Pranzo",
    "dinner": "Cena",
}

DAY_NAMES_SHORT: list[str] = ["Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom"]
DAY_NAMES_LONG: list[str] = [
    "Lunedì", "Martedì", "Mercoledì", "Giovedì",
    "Venerdì", "Sabato", "Domenica",
]

MONTH_NAMES_SHORT: list[str] = [
    "Gen", "Feb", "Mar", "Apr", "Mag", "Giu",
    "Lug", "Ago", "Set", "Ott", "Nov", "Dic",
]


def format_day_month(d: date) -> str:
    return f"{d.day} {MONTH_NAMES_SHORT[d.month - 1]}"
