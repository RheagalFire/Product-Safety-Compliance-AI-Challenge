"""Minimal async PubChem PUG REST client.

Two endpoints:
  - name   -> CIDs:  /compound/name/{name}/cids/JSON
  - formula -> CIDs: /compound/fastformula/{formula}/cids/JSON

For the forbidden list we take *all* returned CIDs (a formula like 'C6H6'
can match many isomers; over-flagging is the safer error mode for a
compliance system).
"""

from urllib.parse import quote

import httpx

from app.observability import observe

BASE = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"


class PubChemClient:
    def __init__(self, timeout: float = 8.0, max_records: int = 50):
        self._client = httpx.AsyncClient(timeout=timeout)
        self.max_records = max_records

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _cids(self, url: str) -> list[int]:
        try:
            r = await self._client.get(url)
        except httpx.HTTPError:
            return []
        # PubChem returns 404 for unknown names, 400 for unparseable formulas,
        # and intermittent 5xx under load. In all cases degrade gracefully —
        # Layer C judge will still see the surface form.
        if r.status_code >= 400:
            return []
        try:
            data = r.json()
        except ValueError:
            return []
        return list(data.get("IdentifierList", {}).get("CID", []) or [])

    @observe(name="tool.pubchem.name")
    async def cids_for_name(self, name: str) -> list[int]:
        url = f"{BASE}/compound/name/{quote(name, safe='')}/cids/JSON"
        return (await self._cids(url))[: self.max_records]

    @observe(name="tool.pubchem.formula")
    async def cids_for_formula(self, formula: str) -> list[int]:
        url = f"{BASE}/compound/fastformula/{quote(formula, safe='')}/cids/JSON"
        return (await self._cids(url))[: self.max_records]
