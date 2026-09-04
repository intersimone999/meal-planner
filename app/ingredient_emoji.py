"""Best-effort ingredient classification for Italian shopping names.

Presentation-only (SPEC.md §3.5, §4.4) — nothing is persisted. Each
keyword carries an emoji and a supermarket-department id; both are
matched via whole-word, accent-insensitive lookup against the ingredient
name. Unknowns fall back to "" (no emoji) and the "altro" department.

Rules:
- Order in _TABLE matters. Multi-word / more-specific keys come first
  (e.g. "pesce spada" wins over "pesce").
- Whole-word match via \\b in the normalized (lowercased, accent-stripped)
  name — so "pomelo" does NOT hit "mela".
- Italian singular and plural forms are both listed where relevant.
"""

from __future__ import annotations

import re
import unicodedata

# ---------------------------------------------------------------------------
# Departments — displayed in this order (supermarket store-flow), matching
# SPEC.md §3.5. Only non-empty depts render on the shopping page.
# ---------------------------------------------------------------------------

DEPARTMENTS: list[str] = [
    "frutta_verdura",
    "panetteria",
    "pasta_riso",
    "latticini_uova",
    "salumi",
    "carne",
    "pesce",
    "surgelati",
    "scatolame",
    "condimenti",
    "dolci",
    "bevande",
    "pulizia",
    "altro",
]

DEPARTMENT_LABELS: dict[str, str] = {
    "frutta_verdura":  "Frutta e verdura",
    "panetteria":      "Panetteria",
    "pasta_riso":      "Pasta e riso",
    "latticini_uova":  "Latticini e uova",
    "salumi":          "Salumi",
    "carne":           "Carne",
    "pesce":           "Pesce",
    "surgelati":       "Surgelati",
    "scatolame":       "Scatolame e conserve",
    "condimenti":      "Condimenti",
    "dolci":           "Dolci",
    "bevande":         "Bevande",
    "pulizia":         "Casa e pulizia",
    "altro":           "Altro",
}

DEPARTMENT_EMOJIS: dict[str, str] = {
    "frutta_verdura":  "🥦",
    "panetteria":      "🥖",
    "pasta_riso":      "🍝",
    "latticini_uova":  "🧀",
    "salumi":          "🥓",
    "carne":           "🥩",
    "pesce":           "🐟",
    "surgelati":       "🧊",
    "scatolame":       "🥫",
    "condimenti":      "🫒",
    "dolci":           "🍫",
    "bevande":         "🍷",
    "pulizia":         "🧴",
    "altro":           "🛒",
}

# Aliases for compactness in the table below.
FV = "frutta_verdura"
PN = "panetteria"
PR = "pasta_riso"
LU = "latticini_uova"
SL = "salumi"
CA = "carne"
PE = "pesce"
SG = "surgelati"
SC = "scatolame"
CO = "condimenti"
DO = "dolci"
BE = "bevande"
PU = "pulizia"

# ---------------------------------------------------------------------------
# Keyword table: (keyword, emoji, department)
# Keyword must be lowercased and accent-free. Multi-word / disambiguating
# entries FIRST so specificity wins.
# ---------------------------------------------------------------------------

_TABLE: list[tuple[str, str, str]] = [
    # ---- Multi-word / disambiguating entries first ---------------------
    ("pesce spada",        "🗡️", PE),
    ("olio extravergine",  "🫒", CO),
    ("olio d'oliva",       "🫒", CO),
    ("olio di oliva",      "🫒", CO),
    ("olio di semi",       "🫙", CO),
    ("pomodori pelati",    "🍅", SC),
    ("frutti di bosco",    "🫐", FV),
    ("frutti di mare",     "🦞", PE),
    ("crema di latte",     "🥛", LU),
    ("panna montata",      "🍦", LU),
    ("succo d'arancia",    "🧃", BE),
    ("acqua tonica",       "🥤", BE),
    ("acqua frizzante",    "💧", BE),
    ("caffe decaffeinato", "☕", BE),
    ("carta igienica",     "🧻", PU),
    ("noce moscata",       "🌰", CO),
    ("hot dog",            "🌭", SL),

    # ---- Fruit → frutta_verdura ---------------------------------------
    ("mela", "🍎", FV), ("mele", "🍎", FV),
    ("pera", "🍐", FV), ("pere", "🍐", FV),
    ("arancia", "🍊", FV), ("arance", "🍊", FV), ("mandarino", "🍊", FV), ("mandarini", "🍊", FV),
    ("limone", "🍋", FV), ("limoni", "🍋", FV), ("lime", "🍋", FV),
    ("banana", "🍌", FV), ("banane", "🍌", FV),
    ("uva", "🍇", FV), ("uvetta", "🍇", FV),
    ("fragola", "🍓", FV), ("fragole", "🍓", FV),
    ("ciliegia", "🍒", FV), ("ciliegie", "🍒", FV), ("ciliegio", "🍒", FV),
    ("pesca", "🍑", FV), ("pesche", "🍑", FV),
    ("albicocca", "🍑", FV), ("albicocche", "🍑", FV),
    ("melone", "🍈", FV), ("meloni", "🍈", FV),
    ("anguria", "🍉", FV), ("angurie", "🍉", FV), ("cocomero", "🍉", FV),
    ("ananas", "🍍", FV),
    ("kiwi", "🥝", FV),
    ("cocco", "🥥", FV),
    ("fico", "🍑", FV), ("fichi", "🍑", FV),
    ("mirtillo", "🫐", FV), ("mirtilli", "🫐", FV),
    ("lampone", "🫐", FV), ("lamponi", "🫐", FV),
    ("mora", "🫐", FV), ("more", "🫐", FV),

    # ---- Vegetables → frutta_verdura ----------------------------------
    ("pomodoro", "🍅", FV), ("pomodori", "🍅", FV), ("pomodorini", "🍅", FV),
    ("insalata", "🥬", FV), ("lattuga", "🥬", FV), ("valeriana", "🥬", FV), ("rucola", "🥬", FV),
    ("spinaci", "🥬", FV), ("spinacio", "🥬", FV),
    ("cetriolo", "🥒", FV), ("cetrioli", "🥒", FV), ("zucchina", "🥒", FV), ("zucchine", "🥒", FV),
    ("peperone", "🫑", FV), ("peperoni", "🫑", FV),
    ("peperoncino", "🌶️", CO), ("peperoncini", "🌶️", CO),
    ("melanzana", "🍆", FV), ("melanzane", "🍆", FV),
    ("carota", "🥕", FV), ("carote", "🥕", FV),
    ("broccoli", "🥦", FV), ("broccolo", "🥦", FV), ("cavolfiore", "🥦", FV), ("cavolo", "🥦", FV),
    ("aglio", "🧄", FV),
    ("cipolla", "🧅", FV), ("cipolle", "🧅", FV), ("scalogno", "🧅", FV), ("porro", "🧅", FV),
    ("patata", "🥔", FV), ("patate", "🥔", FV),
    ("mais", "🌽", FV), ("granoturco", "🌽", FV),
    ("zucca", "🎃", FV), ("zucche", "🎃", FV),
    ("funghi", "🍄", FV), ("fungo", "🍄", FV), ("funghetti", "🍄", FV),
    ("porcini", "🍄", FV), ("champignon", "🍄", FV),
    ("carciofo", "🌿", FV), ("carciofi", "🌿", FV),
    ("sedano", "🌿", FV),
    ("finocchio", "🌿", FV), ("finocchi", "🌿", FV),
    ("asparagi", "🌿", FV), ("asparago", "🌿", FV),
    ("fagiolini", "🫘", FV),

    # ---- Herbs → frutta_verdura (fresh) --------------------------------
    ("basilico", "🌿", FV),
    ("prezzemolo", "🌿", FV),
    ("salvia", "🌿", FV),
    ("rosmarino", "🌿", FV),
    ("timo", "🌿", FV),
    ("menta", "🌿", FV),
    ("origano", "🌿", CO),  # usually dried
    ("olive", "🫒", FV), ("oliva", "🫒", FV),

    # ---- Spices & basics → condimenti ---------------------------------
    ("sale", "🧂", CO),
    ("pepe", "🌶️", CO),
    ("zenzero", "🫚", CO),
    ("cannella", "🥮", CO),

    # ---- Meat → carne -------------------------------------------------
    ("manzo", "🥩", CA), ("vitello", "🥩", CA), ("bistecca", "🥩", CA), ("bistecche", "🥩", CA),
    ("hamburger", "🍔", CA),
    ("pollo", "🍗", CA), ("tacchino", "🍗", CA),
    ("agnello", "🍖", CA),
    ("maiale", "🥓", CA),

    # ---- Salumi → salumi ----------------------------------------------
    ("prosciutto", "🥓", SL), ("pancetta", "🥓", SL), ("guanciale", "🥓", SL), ("speck", "🥓", SL),
    ("salsiccia", "🌭", SL), ("salsicce", "🌭", SL), ("wurstel", "🌭", SL),
    ("salame", "🥓", SL), ("mortadella", "🥓", SL), ("bresaola", "🥓", SL),

    # ---- Fish & seafood → pesce ---------------------------------------
    ("tonno", "🐟", PE),
    ("salmone", "🐟", PE),
    ("branzino", "🐟", PE), ("orata", "🐟", PE), ("nasello", "🐟", PE), ("merluzzo", "🐟", PE),
    ("pesce", "🐟", PE),
    ("gambero", "🦐", PE), ("gamberi", "🦐", PE), ("gamberetto", "🦐", PE), ("gamberetti", "🦐", PE),
    ("scampi", "🦐", PE),
    ("cozza", "🦪", PE), ("cozze", "🦪", PE),
    ("vongola", "🦪", PE), ("vongole", "🦪", PE),
    ("calamaro", "🦑", PE), ("calamari", "🦑", PE),
    ("seppia", "🦑", PE), ("seppie", "🦑", PE),
    ("polpo", "🐙", PE), ("polipo", "🐙", PE),
    ("granchio", "🦀", PE),
    ("aragosta", "🦞", PE),
    ("acciuga", "🐟", PE), ("acciughe", "🐟", PE), ("alici", "🐟", PE),

    # ---- Dairy & eggs → latticini_uova --------------------------------
    ("latte", "🥛", LU),
    ("yogurt", "🥛", LU),
    ("burro", "🧈", LU),
    ("formaggio", "🧀", LU), ("formaggi", "🧀", LU),
    ("parmigiano", "🧀", LU), ("grana", "🧀", LU), ("pecorino", "🧀", LU),
    ("mozzarella", "🧀", LU), ("stracchino", "🧀", LU), ("scamorza", "🧀", LU), ("provola", "🧀", LU),
    ("gorgonzola", "🧀", LU), ("ricotta", "🧀", LU), ("mascarpone", "🧀", LU),
    ("uovo", "🥚", LU), ("uova", "🥚", LU),

    # ---- Bread → panetteria -------------------------------------------
    ("pane", "🍞", PN), ("panino", "🥖", PN), ("panini", "🥖", PN), ("baguette", "🥖", PN),
    ("cornetto", "🥐", PN), ("croissant", "🥐", PN),
    ("pizza", "🍕", PN), ("focaccia", "🍞", PN),
    ("cracker", "🍘", PN),

    # ---- Pasta & rice & cereals → pasta_riso --------------------------
    ("riso", "🍚", PR),
    ("pasta", "🍝", PR), ("spaghetti", "🍝", PR), ("penne", "🍝", PR), ("rigatoni", "🍝", PR),
    ("linguine", "🍝", PR), ("fusilli", "🍝", PR), ("tagliatelle", "🍝", PR),
    ("lasagne", "🍝", PR), ("lasagna", "🍝", PR),
    ("gnocchi", "🥟", PR), ("ravioli", "🥟", PR), ("tortellini", "🥟", PR),
    ("farina", "🌾", PR),
    ("cereali", "🥣", PR),
    ("avena", "🌾", PR),
    ("orzo", "🌾", PR),

    # ---- Legumes (canned/dry) → scatolame -----------------------------
    ("fagioli", "🫘", SC),
    ("ceci", "🫘", SC),
    ("lenticchie", "🫘", SC),
    ("piselli", "🫛", SC),

    # ---- Nuts → scatolame ---------------------------------------------
    ("noci", "🌰", SC), ("noce", "🌰", SC),
    ("mandorle", "🌰", SC), ("mandorla", "🌰", SC),
    ("nocciole", "🌰", SC), ("nocciola", "🌰", SC),
    ("pinoli", "🌰", SC),

    # ---- Sweets → dolci -----------------------------------------------
    ("cioccolato", "🍫", DO), ("cacao", "🍫", DO),
    ("biscotti", "🍪", DO), ("biscotto", "🍪", DO), ("cookies", "🍪", DO),
    ("torta", "🍰", DO), ("dolce", "🍰", DO), ("crostata", "🍰", DO),
    ("miele", "🍯", DO),
    ("zucchero", "🍬", DO),
    ("gelato", "🍦", DO),
    ("marmellata", "🍯", DO), ("confettura", "🍯", DO),

    # ---- Beverages → bevande ------------------------------------------
    ("acqua", "💧", BE),
    ("vino", "🍷", BE),
    ("birra", "🍺", BE),
    ("caffe", "☕", BE), ("caffè", "☕", BE),
    ("te", "🍵", BE), ("tè", "🍵", BE), ("tisana", "🍵", BE),
    ("succo", "🧃", BE),

    # ---- Sauces & condiments → condimenti -----------------------------
    ("olio", "🫒", CO),
    ("aceto", "⚗️", CO),
    ("pesto", "🌿", CO),
    ("ragu", "🍝", CO), ("ragù", "🍝", CO),
    ("besciamella", "🥛", CO),
    ("salsa", "🥫", CO),
    ("ketchup", "🥫", CO),
    ("maionese", "🥫", CO),
    ("senape", "🌶️", CO),

    # ---- Household / cleaning → pulizia -------------------------------
    ("detersivo", "🧴", PU), ("detersivi", "🧴", PU),
    ("sapone", "🧼", PU), ("saponetta", "🧼", PU),
    ("ammorbidente", "🧴", PU),
    ("candeggina", "🧴", PU),
    ("disinfettante", "🧴", PU),
    ("spugna", "🧽", PU), ("spugne", "🧽", PU), ("spugnetta", "🧽", PU), ("spugnette", "🧽", PU),
    ("tovaglioli", "🧻", PU), ("tovagliolo", "🧻", PU),
    ("fazzoletti", "🧻", PU), ("fazzoletto", "🧻", PU),
    ("scottex", "🧻", PU),
    ("sacchetti", "🗑️", PU), ("sacchetto", "🗑️", PU),
    ("dentifricio", "🪥", PU),
    ("spazzolino", "🪥", PU),
    ("shampoo", "🧴", PU),
    ("balsamo", "🧴", PU),
    ("deodorante", "🧴", PU),
    ("bagnoschiuma", "🧴", PU),
    ("crema", "🧴", PU),  # ambiguous — might mismatch, but rare
    ("pannolini", "🍼", PU),

    # ---- Frozen → surgelati (rare fresh keyword; explicit hits) --------
    ("surgelato", "🧊", SG), ("surgelati", "🧊", SG),
    ("ghiaccio", "🧊", SG),
]


def _normalize(s: str) -> str:
    nfkd = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


_COMPILED: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(rf"\b{re.escape(_normalize(kw))}\b"), emoji, dept)
    for kw, emoji, dept in _TABLE
]


def _match(name: str | None) -> tuple[str, str] | None:
    """Return (emoji, dept) for the first matching keyword, or None."""
    if not name:
        return None
    n = _normalize(name)
    for pattern, emoji, dept in _COMPILED:
        if pattern.search(n):
            return emoji, dept
    return None


def emoji_for(name: str | None) -> str:
    hit = _match(name)
    return hit[0] if hit else ""


def department_for(name: str | None) -> str:
    """Return the supermarket-department id, or 'altro' if unmatched."""
    hit = _match(name)
    return hit[1] if hit else "altro"
