import io
from typing import ClassVar

from app.extraction.raw.base import RawDoc, RawExtractor
from app.observability import observe


class EasyOcrExtractor(RawExtractor):
    """OCR for images and PDFs via easyocr.

    PDFs are rasterized page-by-page with pypdfium2 (pure-python, no poppler).
    The easyocr Reader is lazy-initialized on first use — model weights
    (~100MB) download on first run, then cache locally.
    """

    name: ClassVar[str] = "easyocr"
    supported_mime: ClassVar[set[str]] = {
        "application/pdf",
        "image/png",
        "image/jpeg",
        "image/jpg",
    }

    def __init__(self, languages: list[str] | None = None, gpu: bool = False, render_dpi: int = 200):
        self.languages = languages or ["en"]
        self.gpu = gpu
        self.render_dpi = render_dpi
        self._reader = None  # lazy

    def _get_reader(self):
        if self._reader is None:
            import easyocr

            self._reader = easyocr.Reader(self.languages, gpu=self.gpu, verbose=False)
        return self._reader

    def _ocr_image_bytes(self, png_bytes: bytes) -> str:
        import numpy as np
        from PIL import Image

        img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
        arr = np.array(img)
        lines = self._get_reader().readtext(arr, detail=0, paragraph=True)
        return "\n".join(lines)

    def _rasterize_pdf(self, pdf_bytes: bytes) -> list[bytes]:
        """Render each PDF page to PNG bytes via pypdfium2."""
        import pypdfium2 as pdfium

        scale = self.render_dpi / 72.0
        pages: list[bytes] = []
        doc = pdfium.PdfDocument(pdf_bytes)
        try:
            for page in doc:
                bitmap = page.render(scale=scale)
                pil = bitmap.to_pil()
                buf = io.BytesIO()
                pil.save(buf, format="PNG")
                pages.append(buf.getvalue())
        finally:
            doc.close()
        return pages

    @observe(name="extract.raw.easyocr")
    async def extract(self, file_bytes: bytes, mime: str, filename: str | None) -> RawDoc:
        if mime == "application/pdf" or (filename or "").lower().endswith(".pdf"):
            page_pngs = self._rasterize_pdf(file_bytes)
            page_texts = [self._ocr_image_bytes(p) for p in page_pngs]
            text = "\n\n--- page break ---\n\n".join(page_texts)
            return RawDoc(
                text=text,
                images=page_pngs,
                backend=self.name,
                metadata={"filename": filename, "mime": mime, "pages": len(page_pngs)},
            )
        # image
        text = self._ocr_image_bytes(file_bytes)
        return RawDoc(
            text=text,
            images=[file_bytes],
            backend=self.name,
            metadata={"filename": filename, "mime": mime, "pages": 1},
        )
