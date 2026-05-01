from dataclasses import dataclass

from app.domain.models import ProductExtraction
from app.extraction.raw.base import RawExtractor
from app.extraction.raw.easyocr_extractor import EasyOcrExtractor
from app.extraction.raw.passthrough import PassthroughExtractor
from app.extraction.structured.base import StructuredExtractor
from app.extraction.structured.llm_schema import LlmSchemaExtractor
from app.llm.client import LlmClient
from app.observability import observe


@dataclass
class ExtractionChain:
    raw: RawExtractor | None
    structured: StructuredExtractor


class ExtractionRouter:
    """Picks an extraction chain by file mime + filename. Chains are tried in
    order; on exception the next chain is attempted."""

    def __init__(self, llm: LlmClient, text_model: str, vision_model: str):
        self.llm_schema = LlmSchemaExtractor(llm, text_model)
        self.passthrough = PassthroughExtractor()
        self.easyocr = EasyOcrExtractor()

    def select(self, mime: str, filename: str | None) -> list[ExtractionChain]:
        name = (filename or "").lower()
        if mime in {"text/plain", "text/csv"} or name.endswith((".txt", ".csv", ".md")):
            return [ExtractionChain(raw=self.passthrough, structured=self.llm_schema)]
        if mime == "application/pdf" or name.endswith(".pdf"):
            return [ExtractionChain(raw=self.easyocr, structured=self.llm_schema)]
        if mime.startswith("image/") or name.endswith((".png", ".jpg", ".jpeg")):
            return [ExtractionChain(raw=self.easyocr, structured=self.llm_schema)]
        raise NotImplementedError(f"No extraction chain for mime={mime!r} filename={filename!r}")

    @observe(name="extract")
    async def run(
        self,
        file_bytes: bytes,
        mime: str,
        filename: str | None,
        product_id_hint: str | None = None,
    ) -> ProductExtraction:
        last_err: Exception | None = None
        for chain in self.select(mime, filename):
            try:
                if chain.raw is None:
                    raise RuntimeError("chain.raw is None and bytes-direct path not yet implemented")
                raw = await chain.raw.extract(file_bytes, mime, filename)
                return await chain.structured.to_extraction(raw, product_id_hint=product_id_hint)
            except Exception as e:  # noqa: BLE001 — fallback chain
                last_err = e
        assert last_err is not None
        raise last_err
