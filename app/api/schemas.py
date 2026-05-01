"""Public API request/response models. Kept separate from app.domain.models
so the wire format can evolve without churning internal types."""

from typing import Literal

from pydantic import BaseModel, Field

from app.domain.enums import MatchLayer
from app.domain.models import MatchHit, MatchTrace, ProductExtraction

Method = Literal["exact_match", "pubchem_cid", "llm_judge"]
_LAYER_TO_METHOD: dict[MatchLayer, Method] = {
    MatchLayer.A: "exact_match",
    MatchLayer.B: "pubchem_cid",
    MatchLayer.C: "llm_judge",
}


class ReasonItem(BaseModel):
    forbidden_ingredient: str
    matched_in_product: str
    method: Method
    confidence: float
    rationale: str | None = None  # populated for pubchem_cid / llm_judge


class TraceSummary(BaseModel):
    extraction_backend: str
    extraction_confidence: float
    layers_run: list[MatchLayer]
    short_circuited_at: MatchLayer | None = None


class EvaluateRequest(BaseModel):
    """Sent as JSON in the multipart `payload` form field."""

    file_path: str | None = None
    forbidden_ingredients: list[str] | None = None  # optional override; falls back to default
    ocr_strategy: Literal["easyocr", "gemini_vision"] = "gemini_vision"


class EvaluateResponse(BaseModel):
    product_id: str | None = None
    product_name: str | None = None
    status: Literal["Accepted", "Rejected"]
    reason: list[ReasonItem] = Field(default_factory=list)
    ingredients_detected: list[str] = Field(default_factory=list)
    trace: TraceSummary


def _layers_run(trace: MatchTrace) -> list[MatchLayer]:
    """Derive which layers actually executed from the short-circuit point.
    short=A -> only A; short=B -> A+B; short=C or None -> A+B+C."""
    sc = trace.short_circuited_at
    if sc is MatchLayer.A:
        return [MatchLayer.A]
    if sc is MatchLayer.B:
        return [MatchLayer.A, MatchLayer.B]
    return [MatchLayer.A, MatchLayer.B, MatchLayer.C]


def to_response(
    extraction: ProductExtraction, hits: list[MatchHit], trace: MatchTrace
) -> EvaluateResponse:
    reason = [
        ReasonItem(
            forbidden_ingredient=h.forbidden_entry,
            matched_in_product=h.ingredient.surface_form,
            method=_LAYER_TO_METHOD[h.layer],
            confidence=h.confidence,
            rationale=None if h.layer is MatchLayer.A else h.rationale,
        )
        for h in hits
    ]
    return EvaluateResponse(
        product_id=extraction.product_id,
        product_name=extraction.product_name,
        status="Rejected" if hits else "Accepted",
        reason=reason,
        ingredients_detected=[i.surface_form for i in extraction.ingredients],
        trace=TraceSummary(
            extraction_backend=extraction.source_backend,
            extraction_confidence=extraction.extraction_confidence,
            layers_run=_layers_run(trace),
            short_circuited_at=trace.short_circuited_at,
        ),
    )
