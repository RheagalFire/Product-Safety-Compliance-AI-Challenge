import csv
from pathlib import Path

from pydantic import BaseModel, Field

from app.domain.enums import IngredientKind
from app.matching.normalize import classify, normalize_name, to_hill


class ForbiddenIndex(BaseModel):
    """Indexed forbidden-ingredient list.

    Layer A keys: normalized_names (str -> raw entry), hill_formulas (str -> raw entry).
    Layer B keys: cid_set (PubChem CIDs) + cid_to_entry (CID -> raw entry).
    Layer B fields are populated by Services.build at startup via PubChem.
    """

    raw_entries: list[str] = Field(default_factory=list)
    normalized_names: dict[str, str] = Field(default_factory=dict)
    hill_formulas: dict[str, str] = Field(default_factory=dict)
    cid_set: set[int] = Field(default_factory=set)
    cid_to_entry: dict[int, str] = Field(default_factory=dict)

    @classmethod
    def from_csv(cls, path: Path) -> "ForbiddenIndex":
        idx = cls()
        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                entry = (row.get("ingredient") or "").strip().strip('"')
                if not entry:
                    continue
                idx.raw_entries.append(entry)
                if classify(entry) is IngredientKind.FORMULA:
                    idx.hill_formulas[to_hill(entry)] = entry
                else:
                    idx.normalized_names[normalize_name(entry)] = entry
        return idx
