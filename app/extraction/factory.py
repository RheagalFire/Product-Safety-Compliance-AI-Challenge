from dataclasses import dataclass
from typing import Literal

from app.api.events import emit
from app.domain.models import ProductExtraction
from app.extraction.gemini_vision import GeminiVisionExtractor
from app.extraction.raw.base import RawExtractor
from app.extraction.raw.easyocr_extractor import EasyOcrExtractor
from app.extraction.raw.passthrough import PassthroughExtractor
from app.extraction.structured.base import StructuredExtractor
from app.extraction.structured.llm_schema import LlmSchemaExtractor
from app.llm.client import LlmClient
from app.observability import observe

OcrStrategy = Literal["easyocr", "gemini_vision"]


@dataclass
class ExtractionChain:
    """Either two-tier (raw -> structured) OR a single fused extractor."""

    raw: RawExtractor | None = None
    structured: StructuredExtractor | None = None
    fused: GeminiVisionExtractor | None = None


class ExtractionRouter:
    """Picks an extraction chain by file mime + filename, with an OCR
    strategy override (easyocr two-tier vs gemini-vision fused).

    Strategies are pluggable — adding Reducto / Mistral OCR is one new
    class registration."""

    def __init__(self, llm: LlmClient, text_model: str, vision_model: str):
        self.llm_schema = LlmSchemaExtractor(llm, text_model)
        self.passthrough = PassthroughExtractor()
        self.easyocr = EasyOcrExtractor()
        self.gemini_vision = GeminiVisionExtractor(llm, vision_model)

    def select(
        self,
        mime: str,
        filename: str | None,
        strategy: OcrStrategy = "gemini_vision",
    ) -> list[ExtractionChain]:
        name = (filename or "").lower()
        is_text = mime in {"text/plain", "text/csv"} or name.endswith((".txt", ".csv", ".md"))
        is_pdf = mime == "application/pdf" or name.endswith(".pdf")
        is_image = mime.startswith("image/") or name.endswith((".png", ".jpg", ".jpeg"))

        if is_text:
            # txt always goes passthrough+llm regardless of strategy
            return [ExtractionChain(raw=self.passthrough, structured=self.llm_schema)]

        if is_pdf or is_image:
            if strategy == "gemini_vision":
                return [ExtractionChain(fused=self.gemini_vision)]
            # default: easyocr two-tier
            return [ExtractionChain(raw=self.easyocr, structured=self.llm_schema)]

        raise NotImplementedError(f"No extraction chain for mime={mime!r} filename={filename!r}")

    @observe(name="extract")
    async def run(
        self,
        file_bytes: bytes,
        mime: str,
        filename: str | None,
        product_id_hint: str | None = None,
        strategy: OcrStrategy = "gemini_vision",
    ) -> ProductExtraction:
        await emit("Cracking open the specimen", stage="extract")
        last_err: Exception | None = None
        for chain in self.select(mime, filename, strategy):
            try:
                if chain.fused is not None:
                    extraction = await chain.fused.extract(
                        file_bytes, mime, filename, product_id_hint=product_id_hint
                    )
                else:
                    if chain.raw is None or chain.structured is None:
                        raise RuntimeError("malformed extraction chain")
                    if isinstance(chain.raw, EasyOcrExtractor):
                        await emit("Doing tough OCR", stage="extract", backend="easyocr")
                    raw = await chain.raw.extract(file_bytes, mime, filename)
                    await emit("Reading the chemistry off the label", stage="extract")
                    extraction = await chain.structured.to_extraction(
                        raw, product_id_hint=product_id_hint
                    )
                await emit(
                    f"Specimen labelled · {len(extraction.ingredients)} ingredients",
                    stage="extract",
                    ingredient_count=len(extraction.ingredients),
                )
                return extraction
            except Exception as e:  # noqa: BLE001 — fallback chain
                last_err = e
        assert last_err is not None
        raise last_err
