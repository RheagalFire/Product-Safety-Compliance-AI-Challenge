"""Gemini-vision fused extractor: bytes → ProductExtraction in one LLM call.

Replaces the easyocr→llm two-step pipeline with a single multimodal call.
PDFs are rasterized via pypdfium2 (pure-python, no system deps); each page
becomes a base64-encoded PNG attached to the prompt. Plain text falls back
to a text-only call.

Use this when memory is tight (no torch / cv2 / 100 MB model download) and
when label OCR quality matters (Gemini's vision outperforms easyocr on
realistic product packaging).
"""

import base64
import io
from typing import ClassVar

from app.api.events import emit
from app.domain.models import ProductExtraction
from app.llm.client import LlmClient
from app.observability import observe

SYSTEM_PROMPT = (
    "You receive a product label as text and/or images. Extract the structured "
    "product safety data. Return ONLY ingredients/chemicals listed on the "
    "label as IngredientMention rows — preserve each ingredient's surface "
    "form VERBATIM (do not rewrite 'C6H6' to 'Benzene' or vice versa). "
    "Classify kind as 'formula' for molecular formulas (e.g. C6H6, H2O2, "
    "C8H10N4O2), 'name' for trade/INCI/common names (e.g. Methylparaben, "
    "Sodium Lauryl Sulfate, Caffeine), 'unknown' only if you truly cannot "
    "tell. Set source_backend to the value the user provides. Set "
    "extraction_confidence in [0,1] reflecting how confident you are."
)


def _rasterize_pdf(pdf_bytes: bytes, dpi: int = 180, max_pages: int = 4) -> list[bytes]:
    """PDF → list of PNG page bytes (capped to first `max_pages`)."""
    import pypdfium2 as pdfium

    scale = dpi / 72.0
    pages: list[bytes] = []
    doc = pdfium.PdfDocument(pdf_bytes)
    try:
        for page in list(doc)[:max_pages]:
            buf = io.BytesIO()
            page.render(scale=scale).to_pil().save(buf, format="PNG")
            pages.append(buf.getvalue())
    finally:
        doc.close()
    return pages


def _data_url(png_bytes: bytes, mime: str = "image/png") -> str:
    return f"data:{mime};base64,{base64.b64encode(png_bytes).decode('ascii')}"


class GeminiVisionExtractor:
    """Fused vision extractor — implements the same contract as the
    two-tier easyocr+llm chain but in a single call."""

    name: ClassVar[str] = "gemini_vision"

    def __init__(self, llm: LlmClient, model: str):
        self.llm = llm
        self.model = model

    @observe(name="extract.fused.gemini_vision")
    async def extract(
        self,
        file_bytes: bytes,
        mime: str,
        filename: str | None,
        product_id_hint: str | None = None,
    ) -> ProductExtraction:
        backend_tag = f"gemini_vision:{self.model}"
        await emit("Squinting at pixels with Gemini", stage="extract", backend="gemini_vision")

        # Build multimodal user content
        text_part = (
            f"product_id_hint: {product_id_hint or 'unknown'}\n"
            f"source_backend: {backend_tag}\n\n"
            "Extract the ingredient list from the product label."
        )
        content: list[dict] = [{"type": "text", "text": text_part}]

        is_pdf = mime == "application/pdf" or (filename or "").lower().endswith(".pdf")
        is_image = mime.startswith("image/") or (filename or "").lower().endswith(
            (".png", ".jpg", ".jpeg")
        )

        if is_pdf:
            for png in _rasterize_pdf(file_bytes):
                content.append({"type": "image_url", "image_url": {"url": _data_url(png)}})
        elif is_image:
            img_mime = mime if mime.startswith("image/") else "image/png"
            content.append(
                {"type": "image_url", "image_url": {"url": _data_url(file_bytes, img_mime)}}
            )
        else:
            # text/csv — append the raw text inline
            content[0]["text"] += "\n\n--- DOCUMENT ---\n" + file_bytes.decode(
                "utf-8", errors="replace"
            )

        await emit("Reading the label", stage="extract", backend="gemini_vision")
        extraction = await self.llm.structured(
            model=self.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": content},
            ],
            schema=ProductExtraction,
            reasoning_effort="low",
            max_tokens=4096,
        )
        if not extraction.raw_text:
            # Vision didn't surface raw text; leave empty (extraction is still valid)
            extraction.raw_text = ""
        extraction.source_backend = backend_tag
        return extraction
