"""Layer C — single batched LLM judge call across all Layer-B residuals.

Instead of N independent calls (one per residual), we send the whole list of
unresolved ingredients × the forbidden list in a single structured call and
get back a cross-table of verdicts. Faster and cheaper than N parallel calls,
and the model gets to compare ingredients side-by-side which improves
consistency.
"""

from app.domain.enums import MatchLayer, ResolutionSource
from app.domain.models import BatchVerdict, MatchHit, ResolvedIngredient
from app.llm.client import LlmClient
from app.matching.forbidden_index import ForbiddenIndex
from app.observability import observe

JUDGE_SYSTEM = (
    "You are a chemistry compliance judge. For EACH ingredient in the input "
    "list, decide whether it is chemically EQUIVALENT to any compound on the "
    "forbidden list (i.e. the same chemical entity expressed under a different "
    "name, abbreviation, IUPAC form, or molecular formula).\n\n"
    "Be strict: morphologically similar but chemically distinct compounds "
    "(e.g. Methylparaben vs Ethylparaben, sucrose C12H22O11 vs glucose "
    "C6H12O6) are NOT equivalent. Set is_forbidden=true only when confident; "
    "matched_forbidden_entry must be the EXACT string from the forbidden list. "
    "Set confidence in [0,1].\n\n"
    "Echo `ingredient` verbatim from the input. Return one verdict per "
    "ingredient, in the same order."
)


class LayerCJudge:
    def __init__(self, llm: LlmClient, model: str, confidence_threshold: float = 0.7):
        self.llm = llm
        self.model = model
        self.confidence_threshold = confidence_threshold

    @observe(name="layer_c.judge_batch")
    async def judge_batch(self, surfaces: list[str], forbidden: list[str]) -> BatchVerdict:
        user = (
            f"Ingredients to judge ({len(surfaces)}):\n"
            + "\n".join(f"{i + 1}. {s}" for i, s in enumerate(surfaces))
            + f"\n\nForbidden compounds ({len(forbidden)}):\n"
            + "\n".join(f"- {e}" for e in forbidden)
        )
        return await self.llm.structured(
            model=self.model,
            messages=[
                {"role": "system", "content": JUDGE_SYSTEM},
                {"role": "user", "content": user},
            ],
            schema=BatchVerdict,
            reasoning_effort="minimal",
            max_tokens=4096,
        )


@observe(name="match.layer_c")
async def match_layer_c(
    residuals: list[ResolvedIngredient],
    index: ForbiddenIndex,
    judge: LayerCJudge,
    max_to_judge: int = 30,
) -> tuple[list[MatchHit], list[ResolvedIngredient]]:
    """One batched LLM call across the cross-table of residuals × forbidden.
    Anything beyond `max_to_judge` stays unresolved (cheap guard against
    pathological OCR tail; the forbidden list is small so 30 is plenty)."""
    if not residuals:
        return [], []

    forbidden = sorted(set(index.raw_entries))
    targets = residuals[:max_to_judge]
    overflow = residuals[max_to_judge:]

    result = await judge.judge_batch([r.surface_form for r in targets], forbidden)
    by_surface = {v.ingredient: v for v in result.verdicts}

    hits: list[MatchHit] = []
    unresolved: list[ResolvedIngredient] = list(overflow)

    for r in targets:
        v = by_surface.get(r.surface_form)
        if (
            v is not None
            and v.is_forbidden
            and v.matched_forbidden_entry
            and v.confidence >= judge.confidence_threshold
        ):
            r_marked = r.model_copy(update={"resolution_source": ResolutionSource.AGENT})
            hits.append(
                MatchHit(
                    ingredient=r_marked,
                    forbidden_entry=v.matched_forbidden_entry,
                    layer=MatchLayer.C,
                    confidence=v.confidence,
                    rationale=v.rationale,
                )
            )
        else:
            unresolved.append(r)

    return hits, unresolved
