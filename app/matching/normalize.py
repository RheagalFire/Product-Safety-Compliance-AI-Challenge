import re
from collections import Counter

from app.domain.enums import IngredientKind

# Periodic table — full set of valid element symbols. Used to validate molecular formulas.
ELEMENTS: frozenset[str] = frozenset(
    """
    H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn Fe Co Ni
    Cu Zn Ga Ge As Se Br Kr Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb Te I Xe
    Cs Ba La Ce Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu Hf Ta W Re Os Ir Pt Au
    Hg Tl Pb Bi Po At Rn Fr Ra Ac Th Pa U Np Pu Am Cm Bk Cf Es Fm Md No Lr Rf
    Db Sg Bh Hs Mt Ds Rg Cn Nh Fl Mc Lv Ts Og
    """.split()
)

_FORMULA_SHAPE_RE = re.compile(r"^(?:[A-Z][a-z]?\d*)+$")
_FORMULA_TOKEN_RE = re.compile(r"([A-Z][a-z]?)(\d*)")
_PUNCT_RE = re.compile(r"[\s,\-_/().]+")


def is_formula(s: str) -> bool:
    """True if s parses as a molecular formula whose every token is a real element symbol.
    Excludes trade abbreviations like BHA/BHT (B+H+A: 'A' is not an element)."""
    s = s.strip()
    if not s or not _FORMULA_SHAPE_RE.match(s):
        return False
    tokens = _FORMULA_TOKEN_RE.findall(s)
    return all(el in ELEMENTS for el, _ in tokens if el)


def to_hill(formula: str) -> str:
    """Canonical Hill notation: C first, H second, rest alphabetical. '1' counts dropped."""
    counts: Counter[str] = Counter()
    for el, n in _FORMULA_TOKEN_RE.findall(formula.strip()):
        if not el:
            continue
        counts[el] += int(n) if n else 1

    def fmt(el: str) -> str:
        n = counts[el]
        return f"{el}{n if n > 1 else ''}"

    parts: list[str] = []
    if "C" in counts:
        parts.append(fmt("C"))
    if "H" in counts:
        parts.append(fmt("H"))
    parts.extend(fmt(el) for el in sorted(counts) if el not in {"C", "H"})
    return "".join(parts)


def normalize_name(s: str) -> str:
    """Lowercase, drop punctuation/whitespace. '1,4-Dioxane' -> '14dioxane'."""
    return _PUNCT_RE.sub("", s.strip().lower())


def classify(s: str) -> IngredientKind:
    if is_formula(s):
        return IngredientKind.FORMULA
    if s.strip():
        return IngredientKind.NAME
    return IngredientKind.UNKNOWN
