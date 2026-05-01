from abc import ABC, abstractmethod
from typing import ClassVar

from app.domain.models import ProductExtraction
from app.extraction.raw.base import RawDoc


class StructuredExtractor(ABC):
    name: ClassVar[str]

    @abstractmethod
    async def to_extraction(
        self, raw: RawDoc, product_id_hint: str | None = None
    ) -> ProductExtraction: ...
