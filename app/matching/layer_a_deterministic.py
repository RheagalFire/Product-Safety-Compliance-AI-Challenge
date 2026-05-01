from app.domain.enums import IngredientKind, MatchLayer, ResolutionSource
from app.domain.models import IngredientMention, MatchHit, ResolvedIngredient
from app.matching.forbidden_index import ForbiddenIndex
from app.matching.normalize import classify, normalize_name, to_hill
from app.observability import observe


@observe(name="match.layer_a")
def match_layer_a(
    ingredients: list[IngredientMention],
    index: ForbiddenIndex,
) -> tuple[list[MatchHit], list[IngredientMention]]:
    """Sync, deterministic match: normalize -> exact lookup against index. No I/O."""
    hits: list[MatchHit] = []
    residuals: list[IngredientMention] = []

    for ing in ingredients:
        kind = ing.kind if ing.kind is not IngredientKind.UNKNOWN else classify(ing.surface_form)
        forbidden_entry: str | None = None
        normalized: str
        rationale: str

        if kind is IngredientKind.FORMULA:
            normalized = to_hill(ing.surface_form)
            forbidden_entry = index.hill_formulas.get(normalized)
            rationale = f"Hill formula '{normalized}' matches forbidden '{forbidden_entry}'"
        else:
            normalized = normalize_name(ing.surface_form)
            forbidden_entry = index.normalized_names.get(normalized)
            rationale = f"Normalized name '{normalized}' matches forbidden '{forbidden_entry}'"

        if forbidden_entry:
            hits.append(
                MatchHit(
                    ingredient=ResolvedIngredient(
                        surface_form=ing.surface_form,
                        normalized=normalized,
                        resolution_source=ResolutionSource.NONE,
                    ),
                    forbidden_entry=forbidden_entry,
                    layer=MatchLayer.A,
                    confidence=1.0,
                    rationale=rationale,
                )
            )
        else:
            residuals.append(ing)

    return hits, residuals
