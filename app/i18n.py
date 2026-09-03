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

# Ordered fixed enum: rendering order is meaningful (courses in an Italian meal).
# Used to sort dishes within a planner cell and to populate the recipe-type
# dropdown.
RECIPE_TYPES: list[str] = [
    "antipasto",
    "primo",
    "secondo",
    "contorno",
    "frutta",
    "dolce",
    "altro",
]

RECIPE_TYPE_LABELS: dict[str, str] = {
    "antipasto": "Antipasto",
    "primo":     "Primo",
    "secondo":   "Secondo",
    "contorno":  "Contorno",
    "frutta":    "Frutta",
    "dolce":     "Dolce",
    "altro":     "Altro",
}

# Numeric rank used for sort-order within a slot.
RECIPE_TYPE_RANK: dict[str, int] = {t: i for i, t in enumerate(RECIPE_TYPES)}


def format_day_month(d: date) -> str:
    return f"{d.day} {MONTH_NAMES_SHORT[d.month - 1]}"
