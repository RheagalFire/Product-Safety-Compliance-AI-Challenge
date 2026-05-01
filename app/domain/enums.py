from enum import Enum


class IngredientKind(str, Enum):
    NAME = "name"
    FORMULA = "formula"
    UNKNOWN = "unknown"


class MatchLayer(str, Enum):
    A = "A"
    B = "B"
    C = "C"


class Status(str, Enum):
    ACCEPTED = "Accepted"
    REJECTED = "Rejected"


class ResolutionSource(str, Enum):
    CACHE = "cache"
    PUBCHEM = "pubchem"
    INCI = "inci"
    AGENT = "agent"
    NONE = "none"
