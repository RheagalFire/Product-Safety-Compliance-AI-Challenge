"""Layer C — single LLM judge call per Layer-B residual.

For each residual, ask the model: 'is this ingredient chemically equivalent to
any compound on the forbidden list?'  No tool-calling loop, no embedding
retrieval — the forbidden list is small (~13 entries) so we send the whole
list inline. Calls run concurrently via asyncio.gather.
"""

import asyncio

from app.domain.enums import MatchLayer, ResolutionSource
from app.domain.models import AgentVerdict, MatchHit, ResolvedIngredient
from app.llm.client import LlmClient
from app.matching.forbidden_index import ForbiddenIndex
from app.observability import observe

JUDGE_SYSTEM = (
    "You are a chemistry compliance judge. Given an ingredient (a name or "
    "molecular formula) and a list of forbidden compounds, decide whether the "
    "ingredient is chemically EQUIVALENT to any compound on the forbidden list "
    "(i.e., the same chemical entity expressed under a different name, "
    "abbreviation, IUPAC form, or formula).\n\n"
    "Be strict: morphologically similar but chemically distinct compounds "
    "(e.g., Methylparaben vs Ethylparaben, or sucrose C12H22O11 vs glucose "
    "C6H12O6) are NOT equivalent. Set is_forbidden=true ONLY when you are "
    "confident they refer to the same compound. Set confidence in [0,1].\n\n"
    "If is_forbidden is true, set matched_forbidden_entry to the EXACT string "
    "from the forbidden list. Otherwise leave it null."
)


class LayerCJudge:
    def __init__(self, llm: LlmClient, model: str, confidence_threshold: float = 0.7):
        self.llm = llm
        self.model = model
        self.confidence_threshold = confidence_threshold

    @observe(name="layer_c.judge_one")
    async def judge(self, surface: str, forbidden_list: list[str]) -> AgentVerdict:
        user = (
            f"Ingredient: {surface!r}\n\n"
            "Forbidden compounds:\n" + "\n".join(f"- {e}" for e in forbidden_list)
        )
        return await self.llm.structured(
            model=self.model,
            messages=[
                {"role": "system", "content": JUDGE_SYSTEM},
                {"role": "user", "content": user},
            ],
            schema=AgentVerdict,
        )


@observe(name="match.layer_c")
async def match_layer_c(
    residuals: list[ResolvedIngredient],
    index: ForbiddenIndex,
    judge: LayerCJudge,
    max_to_judge: int = 20,
) -> tuple[list[MatchHit], list[ResolvedIngredient]]:
    """Run the judge on up to `max_to_judge` residuals. Anything beyond the cap
    is returned as still-unresolved so we don't burn LLM cost on noisy OCR
    residue (e.g., 'CHBCOOH', 'C12H22011')."""
    if not residuals:
        return [], []

    forbidden = sorted(set(index.raw_entries))
    targets = residuals[:max_to_judge]
    overflow = residuals[max_to_judge:]

    verdicts = await asyncio.gather(
        *[judge.judge(r.surface_form, forbidden) for r in targets]
    )

    hits: list[MatchHit] = []
    unresolved: list[ResolvedIngredient] = list(overflow)

    for r, v in zip(targets, verdicts, strict=True):
        if (
            v.is_forbidden
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
