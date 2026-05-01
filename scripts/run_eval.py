"""Run the pipeline over every product in product_index.csv and print a
markdown report with per-product verdict, per-layer attribution, latency, and
ground-truth accuracy on the .txt subset (where ingredient lines are
deterministically parseable).

Usage:
  python scripts/run_eval.py
  python scripts/run_eval.py --limit 5
"""

import argparse
import asyncio
import csv
import re
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

PROJ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJ))
load_dotenv(PROJ / ".env")

from app.config import get_settings  # noqa: E402
from app.domain.enums import IngredientKind, MatchLayer  # noqa: E402
from app.matching.forbidden_index import ForbiddenIndex  # noqa: E402
from app.matching.normalize import classify, normalize_name, to_hill  # noqa: E402
from app.services import Services  # noqa: E402

MIME_BY_EXT = {".txt": "text/plain", ".pdf": "application/pdf",
               ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}

INGREDIENT_BLOCK_RE = re.compile(
    r"Ingredients[^\n]*:\s*\n((?:[ \t]*-[^\n]+\n?)+)", re.IGNORECASE
)


def parse_text_ingredients(text: str) -> list[str]:
    m = INGREDIENT_BLOCK_RE.search(text)
    if not m:
        return []
    return [
        ln.strip().lstrip("-").strip()
        for ln in m.group(1).splitlines()
        if ln.strip().startswith("-")
    ]


def expected_layer_a_hits(ingredients: list[str], idx: ForbiddenIndex) -> list[str]:
    """Replicate Layer A purely deterministically — useful as ground truth on
    the txt subset where ingredient lines are reliably extractable."""
    hits: set[str] = set()
    for s in ingredients:
        kind = classify(s)
        if kind is IngredientKind.FORMULA:
            entry = idx.hill_formulas.get(to_hill(s))
        else:
            entry = idx.normalized_names.get(normalize_name(s))
        if entry:
            hits.add(entry)
    return sorted(hits)


async def evaluate_one(svc: Services, file_path: Path):
    file_bytes = file_path.read_bytes()
    mime = MIME_BY_EXT.get(file_path.suffix.lower(), "application/octet-stream")
    t0 = time.perf_counter()
    extraction = await svc.router.run(file_bytes, mime, file_path.name)
    hits, trace = await svc.pipeline.evaluate(extraction)
    return extraction, hits, trace, (time.perf_counter() - t0) * 1000


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--index", default=str(PROJ / "product_index.csv"))
    args = parser.parse_args()

    svc = await Services.build(get_settings())

    rows = list(csv.DictReader(open(args.index)))
    if args.limit:
        rows = rows[: args.limit]

    correct = with_truth = 0
    layer_counts = {"A": 0, "B": 0, "C": 0}
    latencies: list[float] = []
    results: list[dict] = []

    for row in rows:
        pid = row["product_id"]
        rel = row["filename"]
        path = PROJ / rel

        try:
            extraction, hits, trace, latency = await evaluate_one(svc, path)
        except Exception as e:  # noqa: BLE001
            results.append({"id": pid, "type": path.suffix.lstrip("."),
                            "status": "ERROR", "expected": "—", "match": "✗",
                            "hits": str(e)[:80], "expected_hits": "—", "latency_ms": "—"})
            continue

        latencies.append(latency)
        actual = "Rejected" if hits else "Accepted"
        actual_hits = sorted({h.forbidden_entry for h in hits})
        for h in hits:
            layer_counts[h.layer.value] += 1

        expected = "—"
        expected_hits: list[str] = []
        match_marker = "—"
        if path.suffix.lower() == ".txt":
            text = path.read_text(encoding="utf-8", errors="replace")
            expected_hits = expected_layer_a_hits(parse_text_ingredients(text),
                                                  svc.forbidden_index)
            expected = "Rejected" if expected_hits else "Accepted"
            with_truth += 1
            ok = actual == expected
            correct += int(ok)
            match_marker = "✓" if ok else "✗"

        layers_run = "+".join(
            l.value for l in (
                [MatchLayer.A] if trace.short_circuited_at is MatchLayer.A
                else [MatchLayer.A, MatchLayer.B] if trace.short_circuited_at is MatchLayer.B
                else [MatchLayer.A, MatchLayer.B, MatchLayer.C]
            )
        )
        results.append({
            "id": pid, "type": path.suffix.lstrip("."),
            "status": actual, "expected": expected, "match": match_marker,
            "hits": ", ".join(actual_hits) or "—",
            "expected_hits": ", ".join(expected_hits) or "—",
            "layers": layers_run,
            "latency_ms": f"{latency:.0f}",
        })

    print("# Eval report\n")
    print(f"- Products evaluated: **{len(results)}**")
    if with_truth:
        print(f"- Ground-truth accuracy (txt subset): **{correct}/{with_truth} = "
              f"{100*correct/with_truth:.1f}%**")
    print(f"- Hits by layer: A={layer_counts['A']}  B={layer_counts['B']}  C={layer_counts['C']}")
    if latencies:
        latencies.sort()
        p50 = latencies[len(latencies) // 2]
        p95 = latencies[max(0, int(len(latencies) * 0.95) - 1)]
        print(f"- Latency: p50={p50:.0f}ms  p95={p95:.0f}ms")
    print()
    print("| ID | Type | Status | Expected | ✓ | Hits | Expected hits | Layers | Latency |")
    print("|---|---|---|---|---|---|---|---|---|")
    for r in results:
        print(f"| {r['id']} | {r['type']} | {r['status']} | {r['expected']} | "
              f"{r['match']} | {r['hits']} | {r['expected_hits']} | "
              f"{r.get('layers','—')} | {r['latency_ms']}ms |")

    await svc.aclose()
    return 0 if (with_truth == 0 or correct == with_truth) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
