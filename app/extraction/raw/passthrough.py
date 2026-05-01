from typing import ClassVar

from app.extraction.raw.base import RawDoc, RawExtractor
from app.observability import observe


class PassthroughExtractor(RawExtractor):
    name: ClassVar[str] = "passthrough"
    supported_mime: ClassVar[set[str]] = {"text/plain", "text/csv"}

    @observe(name="extract.raw.passthrough")
    async def extract(self, file_bytes: bytes, mime: str, filename: str | None) -> RawDoc:
        text = file_bytes.decode("utf-8", errors="replace")
        return RawDoc(text=text, backend=self.name, metadata={"filename": filename, "mime": mime})
