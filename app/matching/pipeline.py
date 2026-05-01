from app.domain.enums import IngredientKind, MatchLayer, ResolutionSource
from app.domain.models import IngredientMention, MatchHit, MatchTrace, ProductExtraction, ResolvedIngredient
from app.matching.normalize import classify, normalize_name, to_hill
from app.matching.forbidden_index import ForbiddenIndex
from app.matching.layer_a_deterministic import match_layer_a
from app.matching.layer_b_resolver import KnowledgeResolver, match_layer_b
from app.matching.layer_c_judge import LayerCJudge, match_layer_c
from app.observability import observe


def _promote(ing: IngredientMention) -> ResolvedIngredient:
    kind = ing.kind if ing.kind is not IngredientKind.UNKNOWN else classify(ing.surface_form)
    normalized = to_hill(ing.surface_form) if kind is IngredientKind.FORMULA else normalize_name(ing.surface_form)
    return ResolvedIngredient(
        surface_form=ing.surface_form,
        normalized=normalized,
        resolution_source=ResolutionSource.NONE,
    )


class MatchPipeline:
    """Layered matcher: A (deterministic) -> B (PubChem CID) -> C (LLM judge).
    Short-circuits on the first layer to produce hits unless `exhaustive=True`."""

    def __init__(
        self,
        index: ForbiddenIndex,
        resolver: KnowledgeResolver | None = None,
        judge: LayerCJudge | None = None,
        exhaustive: bool = False,
    ):
        self.index = index
        self.resolver = resolver
        self.judge = judge
        self.exhaustive = exhaustive

    @observe(name="match")
    async def evaluate(
        self, extraction: ProductExtraction
    ) -> tuple[list[MatchHit], MatchTrace]:
        # Layer A — deterministic
        a_hits, a_residuals = match_layer_a(extraction.ingredients, self.index)
        if a_hits and not self.exhaustive:
            return a_hits, MatchTrace(layer_a_hits=a_hits, short_circuited_at=MatchLayer.A)

        # Layer B — PubChem CID
        b_hits: list[MatchHit] = []
        b_unresolved: list[ResolvedIngredient] = []
        if self.resolver is not None and a_residuals:
            b_hits, b_unresolved = await match_layer_b(a_residuals, self.index, self.resolver)
        elif a_residuals:
            # Layer B skipped — promote A residuals to ResolvedIngredient so Layer C can run.
            b_unresolved = [_promote(ing) for ing in a_residuals]
        if (a_hits or b_hits) and not self.exhaustive:
            return a_hits + b_hits, MatchTrace(
                layer_a_hits=a_hits,
                layer_b_hits=b_hits,
                unresolved=b_unresolved,
                short_circuited_at=MatchLayer.B if b_hits else MatchLayer.A,
            )

        # Layer C — LLM judge
        c_hits: list[MatchHit] = []
        c_unresolved = b_unresolved
        if self.judge is not None and b_unresolved:
            c_hits, c_unresolved = await match_layer_c(b_unresolved, self.index, self.judge)

        all_hits = a_hits + b_hits + c_hits
        short = (
            MatchLayer.C if c_hits and not self.exhaustive
            else MatchLayer.B if b_hits and not self.exhaustive
            else MatchLayer.A if a_hits and not self.exhaustive
            else None
        )
        return all_hits, MatchTrace(
            layer_a_hits=a_hits,
            layer_b_hits=b_hits,
            layer_c_hits=c_hits,
            unresolved=c_unresolved,
            short_circuited_at=short,
        )
