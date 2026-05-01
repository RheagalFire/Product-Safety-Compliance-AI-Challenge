import json
import mimetypes
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from app.api.schemas import EvaluateRequest, EvaluateResponse, to_response
from app.observability import observe
from app.services import Services

router = APIRouter()


def _services(request: Request) -> Services:
    svc = getattr(request.app.state, "services", None)
    if svc is None:
        raise HTTPException(503, "services not initialized")
    return svc


def _guess_mime(filename: str | None) -> str:
    if not filename:
        return "application/octet-stream"
    mime, _ = mimetypes.guess_type(filename)
    return mime or "application/octet-stream"


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/evaluate_product", response_model=EvaluateResponse)
@observe(name="evaluate_product")
async def evaluate_product(
    request: Request,
    file: UploadFile | None = File(None),
    payload: str | None = Form(None),
) -> EvaluateResponse:
    """Evaluate a product file against the configured forbidden ingredient list.

    Accepts:
      - `file`: multipart upload (txt / pdf / png / jpg)
      - `payload`: optional JSON form field with `EvaluateRequest` shape
        (`file_path` for server-side files, `forbidden_ingredients` to override
        the default list for this request only)
    """
    svc = _services(request)
    body = EvaluateRequest.model_validate_json(payload) if payload else EvaluateRequest()

    if file is not None:
        file_bytes = await file.read()
        filename = file.filename
        mime = file.content_type or _guess_mime(filename)
    elif body.file_path:
        p = Path(body.file_path)
        if not p.exists():
            raise HTTPException(404, f"file_path not found: {body.file_path}")
        file_bytes = p.read_bytes()
        filename = p.name
        mime = _guess_mime(filename)
    else:
        raise HTTPException(400, "provide either `file` upload or payload.file_path")

    extraction = await svc.router.run(file_bytes, mime, filename)
    pipeline = await svc.pipeline_for(body.forbidden_ingredients)
    hits, trace = await pipeline.evaluate(extraction)

    return to_response(extraction, hits, trace)
