"""Layer B — resolve ingredients to PubChem CIDs and match against the
forbidden CID set. In-memory dict cache; ResolvedIngredient.synonyms unused
in this layer (kept on the schema for future Layer C extensions)."""

from app.domain.enums import IngredientKind, MatchLayer, ResolutionSource
from app.domain.models import IngredientMention, MatchHit, ResolvedIngredient
from app.knowledge.pubchem import PubChemClient
from app.matching.forbidden_index import ForbiddenIndex
from app.matching.normalize import classify, normalize_name, to_hill
from app.observability import observe


class KnowledgeResolver:
    def __init__(self, pubchem: PubChemClient):
        self.pubchem = pubchem
        self._cache: dict[tuple[str, str], list[int]] = {}

    @observe(name="resolve.pubchem")
    async def resolve_cids(self, surface: str, kind: IngredientKind) -> tuple[list[int], str]:
        # Always trust classify() over the LLM's hint — see layer_a for why.
        kind = classify(surface)
        if kind is IngredientKind.FORMULA:
            normalized = to_hill(surface)
            key = ("formula", normalized)
            if key not in self._cache:
                self._cache[key] = await self.pubchem.cids_for_formula(normalized)
        else:
            normalized = normalize_name(surface)
            key = ("name", normalized)
            if key not in self._cache:
                self._cache[key] = await self.pubchem.cids_for_name(surface.strip())
        return self._cache[key], normalized


async def resolve_forbidden_index(index: ForbiddenIndex, resolver: KnowledgeResolver) -> None:
    """Populate index.cid_set + cid_to_entry by resolving every forbidden entry to PubChem CIDs."""
    for entry in index.raw_entries:
        kind = classify(entry)
        cids, _ = await resolver.resolve_cids(entry, kind)
        for cid in cids:
            index.cid_set.add(cid)
            index.cid_to_entry.setdefault(cid, entry)


@observe(name="match.layer_b")
async def match_layer_b(
    residuals: list[IngredientMention],
    index: ForbiddenIndex,
    resolver: KnowledgeResolver,
) -> tuple[list[MatchHit], list[ResolvedIngredient]]:
    hits: list[MatchHit] = []
    unresolved: list[ResolvedIngredient] = []

    if not index.cid_set:
        return hits, [
            ResolvedIngredient(
                surface_form=ing.surface_form,
                normalized=ing.surface_form.lower(),
                resolution_source=ResolutionSource.NONE,
            )
            for ing in residuals
        ]

    for ing in residuals:
        cids, normalized = await resolver.resolve_cids(ing.surface_form, ing.kind)
        intersection = set(cids) & index.cid_set
        resolved = ResolvedIngredient(
            surface_form=ing.surface_form,
            normalized=normalized,
            pubchem_cids=cids,
            resolution_source=ResolutionSource.PUBCHEM if cids else ResolutionSource.NONE,
        )
        if intersection:
            cid = next(iter(intersection))
            forbidden_entry = index.cid_to_entry.get(cid, str(cid))
            hits.append(
                MatchHit(
                    ingredient=resolved,
                    forbidden_entry=forbidden_entry,
                    layer=MatchLayer.B,
                    confidence=0.9,
                    rationale=(
                        f"Resolved '{ing.surface_form}' to PubChem CID {cid} "
                        f"matching forbidden '{forbidden_entry}'"
                    ),
                )
            )
        else:
            unresolved.append(resolved)

    return hits, unresolved
