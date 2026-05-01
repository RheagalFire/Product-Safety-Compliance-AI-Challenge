from typing import ClassVar

from app.domain.models import ProductExtraction
from app.extraction.raw.base import RawDoc
from app.extraction.structured.base import StructuredExtractor
from app.llm.client import LlmClient
from app.observability import observe

SYSTEM_PROMPT = (
    "You extract structured product safety data from messy product documents. "
    "Return ONLY ingredients/chemicals listed on the label as IngredientMention rows. "
    "Preserve each ingredient's surface form VERBATIM (do not rewrite 'C6H6' to 'Benzene' or vice versa). "
    "Classify kind as 'formula' for molecular formulas like 'C6H6', 'H2O2', 'C8H10N4O2'; "
    "'name' for trade/INCI/common names like 'Methylparaben', 'Sodium Lauryl Sulfate'; "
    "'unknown' only if you truly cannot tell. "
    "Set source_backend to the value the user provides. "
    "Set extraction_confidence in [0,1] reflecting how confident you are."
)


class LlmSchemaExtractor(StructuredExtractor):
    name: ClassVar[str] = "llm_schema"

    def __init__(self, llm: LlmClient, model: str):
        self.llm = llm
        self.model = model

    @observe(name="extract.structured.llm_schema")
    async def to_extraction(
        self, raw: RawDoc, product_id_hint: str | None = None
    ) -> ProductExtraction:
        backend_tag = f"{raw.backend}+litellm:{self.model}"
        user = (
            f"product_id_hint: {product_id_hint or 'unknown'}\n"
            f"source_backend: {backend_tag}\n\n"
            f"--- RAW DOCUMENT ---\n{raw.text}"
        )
        extraction = await self.llm.structured(
            model=self.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user},
            ],
            schema=ProductExtraction,
        )
        if not extraction.raw_text:
            extraction.raw_text = raw.text
        extraction.source_backend = backend_tag
        return extraction
