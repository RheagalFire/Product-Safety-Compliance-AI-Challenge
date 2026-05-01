from abc import ABC, abstractmethod
from typing import Any, ClassVar

from pydantic import BaseModel, Field


class RawDoc(BaseModel):
    text: str = ""
    images: list[bytes] = Field(default_factory=list)
    backend: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class RawExtractor(ABC):
    name: ClassVar[str]
    supported_mime: ClassVar[set[str]]

    @abstractmethod
    async def extract(self, file_bytes: bytes, mime: str, filename: str | None) -> RawDoc: ...
