from pydantic import BaseModel, Field

from app.domain.enums import IngredientKind, MatchLayer, ResolutionSource, Status


class IngredientMention(BaseModel):
    surface_form: str
    kind: IngredientKind
    line_index: int | None = None


class ProductExtraction(BaseModel):
    product_id: str | None = None
    product_name: str | None = None
    sku: str | None = None
    ingredients: list[IngredientMention] = Field(default_factory=list)
    raw_text: str = ""
    caption: str | None = None
    source_backend: str
    extraction_confidence: float = 1.0


class ResolvedIngredient(BaseModel):
    surface_form: str
    normalized: str
    pubchem_cids: list[int] = Field(default_factory=list)
    synonyms: list[str] = Field(default_factory=list)
    resolution_source: ResolutionSource = ResolutionSource.NONE


class MatchHit(BaseModel):
    ingredient: ResolvedIngredient
    forbidden_entry: str
    layer: MatchLayer
    confidence: float
    rationale: str


class MatchTrace(BaseModel):
    layer_a_hits: list[MatchHit] = Field(default_factory=list)
    layer_b_hits: list[MatchHit] = Field(default_factory=list)
    layer_c_hits: list[MatchHit] = Field(default_factory=list)
    unresolved: list[ResolvedIngredient] = Field(default_factory=list)
    short_circuited_at: MatchLayer | None = None


class AgentVerdict(BaseModel):
    """Layer C LLM judge's verdict on whether a residual ingredient
    is chemically equivalent to any forbidden compound."""

    is_forbidden: bool
    matched_forbidden_entry: str | None = None
    rationale: str
    confidence: float


class EvaluationResult(BaseModel):
    product_name: str | None
    status: Status
    reason: list[str]
    unresolved_ingredients: list[str] = Field(default_factory=list)
    extraction: ProductExtraction
    match_trace: MatchTrace
