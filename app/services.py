import hashlib
import json
from dataclasses import dataclass

from app.config import Settings
from app.domain.enums import IngredientKind
from app.extraction.factory import ExtractionRouter
from app.knowledge.pubchem import PubChemClient
from app.llm.client import LlmClient
from app.matching.forbidden_index import ForbiddenIndex
from app.matching.layer_b_resolver import KnowledgeResolver, resolve_forbidden_index
from app.matching.layer_c_judge import LayerCJudge
from app.matching.normalize import classify, normalize_name, to_hill
from app.matching.pipeline import MatchPipeline


@dataclass
class Services:
    settings: Settings
    llm: LlmClient
    pubchem: PubChemClient
    resolver: KnowledgeResolver
    router: ExtractionRouter
    forbidden_index: ForbiddenIndex
    judge: LayerCJudge
    pipeline: MatchPipeline
    _custom_index_cache: dict[str, ForbiddenIndex]

    @classmethod
    async def build(cls, settings: Settings) -> "Services":
        llm = LlmClient()
        pubchem = PubChemClient()
        resolver = KnowledgeResolver(pubchem)
        router = ExtractionRouter(
            llm=llm,
            text_model=settings.extraction_model,
            vision_model=settings.vision_model,
        )
        index = ForbiddenIndex.from_csv(settings.forbidden_csv)
        await resolve_forbidden_index(index, resolver)
        judge = LayerCJudge(llm=llm, model=settings.primary_text_model)
        pipeline = MatchPipeline(
            index=index, resolver=resolver, judge=judge, exhaustive=settings.exhaustive_match
        )
        return cls(
            settings=settings,
            llm=llm,
            pubchem=pubchem,
            resolver=resolver,
            router=router,
            forbidden_index=index,
            judge=judge,
            pipeline=pipeline,
            _custom_index_cache={},
        )

    async def aclose(self) -> None:
        await self.pubchem.aclose()

    async def pipeline_for(self, additional_forbidden: list[str] | None) -> MatchPipeline:
        """Return a MatchPipeline whose forbidden list is the default plus
        any caller-supplied additions (additive, deduped, cached by content
        hash). Empty / None → default-only pipeline reused."""
        if not additional_forbidden:
            return self.pipeline
        merged = list(self.forbidden_index.raw_entries) + list(additional_forbidden)
        idx = await self._index_for(merged)
        return MatchPipeline(
            index=idx, resolver=self.resolver, judge=self.judge,
            exhaustive=self.settings.exhaustive_match,
        )

    async def _index_for(self, custom_forbidden: list[str]) -> ForbiddenIndex:
        key = hashlib.sha256(
            json.dumps(sorted(set(custom_forbidden))).encode("utf-8")
        ).hexdigest()
        cached = self._custom_index_cache.get(key)
        if cached is not None:
            return cached

        idx = ForbiddenIndex()
        for entry in custom_forbidden:
            entry = entry.strip()
            if not entry:
                continue
            idx.raw_entries.append(entry)
            if classify(entry) is IngredientKind.FORMULA:
                idx.hill_formulas[to_hill(entry)] = entry
            else:
                idx.normalized_names[normalize_name(entry)] = entry
        await resolve_forbidden_index(idx, self.resolver)
        self._custom_index_cache[key] = idx
        return idx
