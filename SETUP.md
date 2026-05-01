# Setup & Run Guide

## Architecture (one paragraph)

A FastAPI service exposes `POST /evaluate_product` that accepts a product file
(`.txt`, `.pdf`, `.png`, `.jpg`) and returns an Accepted/Rejected verdict
plus structured reasons. The pipeline is **extract → match**:

- **Extract**: a routed factory (`app.extraction.factory.ExtractionRouter`)
  picks a backend by file mime — `PassthroughExtractor` for text, `EasyOcrExtractor`
  for PDF/image — then a shared `LlmSchemaExtractor` (Gemini via LiteLLM,
  JSON-schema constrained) emits a `ProductExtraction` Pydantic model.
- **Match**: a 3-layer pipeline (`app.matching.pipeline.MatchPipeline`) with
  short-circuit:
  1. **Layer A** — deterministic Hill-formula + normalized-name match against the forbidden list.
  2. **Layer B** — PubChem CID resolution (live REST, in-memory dict cache); catches synonym/notation mismatches like `C6H6 ↔ Benzene`.
  3. **Layer C** — single LLM judge call per residual (Gemini, structured `AgentVerdict` output); catches the long tail where PubChem can't resolve cleanly (e.g. OCR-garbled formulas).

Every LLM call goes through LiteLLM and is auto-traced to Langfuse via
`litellm.success_callback = ["langfuse"]`; pipeline stages are wrapped with
`@observe` so each request produces a parent trace tree (`evaluate_product → extract → match → match.layer_a/b/c`).

## Quick start (local)

Dependencies are managed with [uv](https://docs.astral.sh/uv/).

```bash
# Install uv if needed: brew install uv  OR  curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync                              # creates .venv from uv.lock

cp .env.example .env
# Set at minimum:
#   GEMINI_API_KEY=...
# Optional (Langfuse observability):
#   LANGFUSE_PUBLIC_KEY=...
#   LANGFUSE_SECRET_KEY=...
#   LANGFUSE_HOST=https://us.cloud.langfuse.com

uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

The first request resolves the 13 forbidden ingredients to PubChem CIDs at
startup (~5–15s, one-time). The first PDF/image request also triggers
EasyOCR's ~100 MB model weights download.

## API examples

**Default forbidden list:**
```bash
curl -s -X POST http://127.0.0.1:8000/evaluate_product \
  -F "file=@texts/P-2025-0004_Ultra_Conditioner.txt"
```

**Custom forbidden list (override per request):**
```bash
curl -s -X POST http://127.0.0.1:8000/evaluate_product \
  -F "file=@texts/P-2025-0004_Ultra_Conditioner.txt" \
  -F 'payload={"forbidden_ingredients":["Benzene","Coumarin"]}'
```

**Server-side file path (no upload):**
```bash
curl -s -X POST http://127.0.0.1:8000/evaluate_product \
  -F 'payload={"file_path":"texts/P-2025-0004_Ultra_Conditioner.txt"}'
```

**Response shape:**
```json
{
  "product_id": "P-2025-0004",
  "product_name": "Ultra Conditioner",
  "status": "Rejected",
  "reason": [
    {"forbidden_ingredient": "C6H6",
     "matched_in_product": "C6H6",
     "method": "exact_match",
     "confidence": 1.0,
     "rationale": null}
  ],
  "ingredients_detected": ["H2O", "C2H5OH", "Sodium Hydroxide", "...", "C6H6", "..."],
  "trace": {
    "extraction_backend": "passthrough+litellm:gemini/gemini-2.5-flash",
    "extraction_confidence": 0.9,
    "layers_run": ["A"],
    "short_circuited_at": "A"
  }
}
```

`method` is one of `exact_match` (Layer A), `pubchem_cid` (Layer B), or
`llm_judge` (Layer C). `rationale` is populated for B and C.

## Eval harness

```bash
uv run python scripts/run_eval.py            # all 30 products
uv run python scripts/run_eval.py --limit 5  # first 5
```

Prints a markdown report with per-product verdict, ground-truth accuracy on
the `.txt` subset (where ingredient lines are deterministically parseable),
per-layer hit counts, and p50/p95 latency.

## Docker

```bash
docker build -t psc .
docker run --rm -p 8000:8000 --env-file .env psc
```

## Repository layout

```
app/
  main.py                       FastAPI factory + lifespan
  config.py                     pydantic-settings (.env-driven)
  observability.py              Langfuse + LiteLLM callback wiring
  api/
    router.py                   POST /evaluate_product
    schemas.py                  Public request/response models
  domain/
    enums.py, models.py         Internal pipeline types
  extraction/
    factory.py                  ExtractionRouter
    raw/{passthrough,easyocr_extractor}.py
    structured/llm_schema.py    LlmSchemaExtractor (gemini structured output)
  matching/
    normalize.py                Hill formula + name normalization
    forbidden_index.py          Indexed forbidden list
    layer_a_deterministic.py
    layer_b_resolver.py         KnowledgeResolver + match_layer_b
    layer_c_judge.py            LayerCJudge + match_layer_c
    pipeline.py                 MatchPipeline (A → B → C with short-circuit)
  knowledge/
    pubchem.py                  Minimal async PubChem PUG REST client
  llm/
    client.py                   Thin litellm wrapper
  services.py                   DI container; pipeline_for(custom_forbidden)
scripts/
  run_eval.py                   Eval harness over product_index.csv
forbidden_ingredients.csv
product_index.csv
texts/, pdfs/, images/
```

## Configuration knobs

All in `app/config.py` / `.env`:

| Env var | Default | Purpose |
|---|---|---|
| `GEMINI_API_KEY` | — | LiteLLM uses this for `gemini/*` models |
| `LANGFUSE_*` | optional | Tracing |
| `EXHAUSTIVE_MATCH` | `false` | If `true`, all 3 layers run even after a hit (full audit instead of fast verdict) |

Models are referenced as plain strings in `Settings.primary_text_model` /
`vision_model`; switching to Anthropic / OpenAI is one config change plus the
matching API key.
