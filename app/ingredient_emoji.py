"""Best-effort emoji picker for Italian ingredient names.

Presentation-only (SPEC.md §4.4) — nothing is persisted. Given a free-text
ingredient name, returns a single-character emoji if any keyword in the
table matches as a whole word (accent- and case-insensitive), else "".

Rules:
- Order matters. Multi-word / more-specific keywords come first so that
  e.g. "pesce spada" hits 🐟 before a generic "pesce" match would.
- Whole-word match via \b in the normalized (lowercased, accent-stripped)
  name — so "MELE ROSSE" matches "mela"/"mele" but "pomelo" does not
  match "mela".
- Keys are Italian singular and plural forms where relevant; add both.
"""

from __future__ import annotations

import re
import unicodedata

# (keyword, emoji). Keyword must be lowercased and accent-free — matched
# with \b keyword \b against the normalized ingredient name.
_TABLE: list[tuple[str, str]] = [
    # ---- Multi-word / disambiguating entries first ---------------------
    ("pesce spada",       "🗡️"),
    ("olio extravergine", "🫒"),
    ("olio d'oliva",      "🫒"),
    ("olio di oliva",     "🫒"),
    ("olio di semi",      "🫙"),
    ("pomodori pelati",   "🍅"),
    ("frutti di bosco",   "🫐"),
    ("frutti di mare",    "🦞"),
    ("crema di latte",    "🥛"),
    ("panna montata",     "🍦"),
    ("succo d'arancia",   "🧃"),
    ("acqua tonica",      "🥤"),
    ("acqua frizzante",   "💧"),
    ("caffe decaffeinato","☕"),

    # ---- Fruit ---------------------------------------------------------
    ("mela",     "🍎"), ("mele", "🍎"),
    ("pera",     "🍐"), ("pere", "🍐"),
    ("arancia",  "🍊"), ("arance", "🍊"), ("mandarino", "🍊"), ("mandarini", "🍊"),
    ("limone",   "🍋"), ("limoni", "🍋"), ("lime", "🍋"),
    ("banana",   "🍌"), ("banane", "🍌"),
    ("uva",      "🍇"), ("uvetta", "🍇"),
    ("fragola",  "🍓"), ("fragole", "🍓"),
    ("ciliegia", "🍒"), ("ciliegie", "🍒"), ("ciliegio", "🍒"),
    ("pesca",    "🍑"), ("pesche", "🍑"), ("albicocca", "🍑"), ("albicocche", "🍑"),
    ("melone",   "🍈"), ("meloni", "🍈"),
    ("anguria",  "🍉"), ("angurie", "🍉"), ("cocomero", "🍉"),
    ("ananas",   "🍍"),
    ("kiwi",     "🥝"),
    ("cocco",    "🥥"),
    ("fico",     "🍑"), ("fichi", "🍑"),
    ("mirtillo", "🫐"), ("mirtilli", "🫐"),
    ("lampone",  "🫐"), ("lamponi", "🫐"),
    ("mora",     "🫐"), ("more", "🫐"),

    # ---- Vegetables ----------------------------------------------------
    ("pomodoro",  "🍅"), ("pomodori", "🍅"), ("pomodorini", "🍅"),
    ("insalata",  "🥬"), ("lattuga", "🥬"), ("valeriana", "🥬"), ("rucola", "🥬"),
    ("spinaci",   "🥬"), ("spinacio", "🥬"),
    ("cetriolo",  "🥒"), ("cetrioli", "🥒"), ("zucchina", "🥒"), ("zucchine", "🥒"),
    ("peperone",  "🫑"), ("peperoni", "🫑"), ("peperoncino", "🌶️"), ("peperoncini", "🌶️"),
    ("melanzana", "🍆"), ("melanzane", "🍆"),
    ("carota",    "🥕"), ("carote", "🥕"),
    ("broccoli",  "🥦"), ("broccolo", "🥦"), ("cavolfiore", "🥦"), ("cavolo", "🥦"),
    ("aglio",     "🧄"),
    ("cipolla",   "🧅"), ("cipolle", "🧅"), ("scalogno", "🧅"), ("porro", "🧅"),
    ("patata",    "🥔"), ("patate", "🥔"),
    ("mais",      "🌽"), ("granoturco", "🌽"),
    ("zucca",     "🎃"), ("zucche", "🎃"),
    ("funghi",    "🍄"), ("fungo", "🍄"), ("funghetti", "🍄"), ("porcini", "🍄"), ("champignon", "🍄"),
    ("carciofo",  "🌿"), ("carciofi", "🌿"),
    ("sedano",    "🌿"),
    ("finocchio", "🌿"), ("finocchi", "🌿"),
    ("asparagi",  "🌿"), ("asparago", "🌿"),
    ("olive",     "🫒"), ("oliva", "🫒"),

    # ---- Herbs & spices ------------------------------------------------
    ("basilico",   "🌿"),
    ("prezzemolo", "🌿"),
    ("origano",    "🌿"),
    ("rosmarino",  "🌿"),
    ("salvia",     "🌿"),
    ("timo",       "🌿"),
    ("menta",      "🌿"),
    ("sale",       "🧂"),
    ("pepe",       "🌶️"),
    ("zenzero",    "🫚"),
    ("cannella",   "🥮"),
    ("noce moscata","🌰"),

    # ---- Meat ----------------------------------------------------------
    ("manzo",       "🥩"), ("vitello", "🥩"), ("bistecca", "🥩"), ("bistecche", "🥩"),
    ("hamburger",   "🍔"),
    ("pollo",       "🍗"), ("tacchino", "🍗"),
    ("agnello",     "🍖"),
    ("maiale",      "🥓"),
    ("prosciutto",  "🥓"), ("pancetta", "🥓"), ("guanciale", "🥓"), ("speck", "🥓"),
    ("salsiccia",   "🌭"), ("salsicce", "🌭"), ("wurstel", "🌭"), ("hot dog", "🌭"),
    ("salame",      "🥓"), ("mortadella", "🥓"), ("bresaola", "🥓"),

    # ---- Fish & seafood ------------------------------------------------
    ("tonno",       "🐟"),
    ("salmone",     "🐟"),
    ("branzino",    "🐟"), ("orata", "🐟"), ("nasello", "🐟"), ("merluzzo", "🐟"),
    ("pesce",       "🐟"),
    ("gambero",     "🦐"), ("gamberi", "🦐"), ("gamberetto", "🦐"), ("gamberetti", "🦐"),
    ("scampi",      "🦐"),
    ("cozza",       "🦪"), ("cozze", "🦪"),
    ("vongola",     "🦪"), ("vongole", "🦪"),
    ("calamaro",    "🦑"), ("calamari", "🦑"), ("seppia", "🦑"), ("seppie", "🦑"), ("polpo", "🐙"), ("polipo", "🐙"),
    ("granchio",    "🦀"),
    ("aragosta",    "🦞"),
    ("acciuga",     "🐟"), ("acciughe", "🐟"), ("alici", "🐟"),

    # ---- Dairy & eggs --------------------------------------------------
    ("latte",       "🥛"),
    ("yogurt",      "🥛"),
    ("burro",       "🧈"),
    ("formaggio",   "🧀"), ("formaggi", "🧀"),
    ("parmigiano",  "🧀"), ("grana", "🧀"), ("pecorino", "🧀"),
    ("mozzarella",  "🧀"), ("stracchino", "🧀"), ("scamorza", "🧀"), ("provola", "🧀"),
    ("gorgonzola",  "🧀"), ("ricotta", "🧀"), ("mascarpone", "🧀"),
    ("uovo",        "🥚"), ("uova", "🥚"),

    # ---- Bread & grains ------------------------------------------------
    ("pane",        "🍞"), ("panino", "🥖"), ("panini", "🥖"), ("baguette", "🥖"),
    ("cornetto",    "🥐"), ("croissant", "🥐"),
    ("pizza",       "🍕"), ("focaccia", "🍞"),
    ("riso",        "🍚"),
    ("pasta",       "🍝"), ("spaghetti", "🍝"), ("penne", "🍝"), ("rigatoni", "🍝"),
    ("linguine",    "🍝"), ("fusilli", "🍝"), ("tagliatelle", "🍝"), ("lasagne", "🍝"), ("lasagna", "🍝"),
    ("gnocchi",     "🥟"), ("ravioli", "🥟"), ("tortellini", "🥟"),
    ("farina",      "🌾"),
    ("cereali",     "🥣"),
    ("avena",       "🌾"),
    ("orzo",        "🌾"),
    ("cracker",     "🍘"),

    # ---- Legumes & nuts ------------------------------------------------
    ("fagioli",     "🫘"), ("fagiolini", "🫘"),
    ("ceci",        "🫘"),
    ("lenticchie",  "🫘"),
    ("piselli",     "🫛"),
    ("noci",        "🌰"), ("noce", "🌰"),
    ("mandorle",    "🌰"), ("mandorla", "🌰"),
    ("nocciole",    "🌰"), ("nocciola", "🌰"),
    ("pinoli",      "🌰"),

    # ---- Sweets / desserts --------------------------------------------
    ("cioccolato",  "🍫"), ("cacao", "🍫"),
    ("biscotti",    "🍪"), ("biscotto", "🍪"), ("cookies", "🍪"),
    ("torta",       "🍰"), ("dolce", "🍰"), ("crostata", "🍰"),
    ("miele",       "🍯"),
    ("zucchero",    "🍬"),
    ("gelato",      "🍦"),
    ("marmellata",  "🍯"), ("confettura", "🍯"),

    # ---- Beverages -----------------------------------------------------
    ("acqua",       "💧"),
    ("vino",        "🍷"),
    ("birra",       "🍺"),
    ("caffe",       "☕"), ("caffè", "☕"),
    ("te",          "🍵"), ("tè", "🍵"), ("tisana", "🍵"),
    ("succo",       "🧃"),

    # ---- Sauces & other -----------------------------------------------
    ("olio",        "🫒"),
    ("aceto",       "⚗️"),
    ("pesto",       "🌿"),
    ("ragu",        "🍝"), ("ragù", "🍝"),
    ("besciamella", "🥛"),
    ("salsa",       "🥫"),
    ("ketchup",     "🥫"),
    ("maionese",    "🥫"),
    ("senape",      "🌶️"),
]


def _normalize(s: str) -> str:
    """Lowercase and strip diacritical marks — accent-insensitive matching."""
    nfkd = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


# Pre-compile the regex patterns once at import time.
_COMPILED: list[tuple[re.Pattern[str], str]] = [
    (re.compile(rf"\b{re.escape(_normalize(kw))}\b"), emoji)
    for kw, emoji in _TABLE
]


def emoji_for(name: str | None) -> str:
    """Return a matching emoji for an ingredient name, or '' if none."""
    if not name:
        return ""
    n = _normalize(name)
    for pattern, emoji in _COMPILED:
        if pattern.search(n):
            return emoji
    return ""
