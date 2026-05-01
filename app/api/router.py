import asyncio
import json
import mimetypes
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse

from app.api.events import EventEmitter, bind_emitter, reset_emitter
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


def _read_input(file: UploadFile | None, body: EvaluateRequest):
    """Resolve (bytes, mime, filename) from either upload or file_path."""
    if file is not None:
        return file, None  # caller will await file.read()
    if body.file_path:
        p = Path(body.file_path)
        if not p.exists():
            raise HTTPException(404, f"file_path not found: {body.file_path}")
        return None, p
    raise HTTPException(400, "provide either `file` upload or payload.file_path")


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


async def _evaluate(svc: Services, file_bytes: bytes, mime: str, filename: str | None,
                    body: EvaluateRequest) -> EvaluateResponse:
    extraction = await svc.router.run(
        file_bytes, mime, filename, strategy=body.ocr_strategy
    )
    pipeline = await svc.pipeline_for(body.forbidden_ingredients)
    hits, trace = await pipeline.evaluate(extraction)
    return to_response(extraction, hits, trace)


@router.post("/evaluate_product", response_model=EvaluateResponse)
@observe(name="evaluate_product")
async def evaluate_product(
    request: Request,
    file: UploadFile | None = File(None),
    payload: str | None = Form(None),
) -> EvaluateResponse:
    svc = _services(request)
    body = EvaluateRequest.model_validate_json(payload) if payload else EvaluateRequest()
    upload, path = _read_input(file, body)
    if upload is not None:
        file_bytes = await upload.read()
        filename = upload.filename
        mime = upload.content_type or _guess_mime(filename)
    else:
        file_bytes = path.read_bytes()
        filename = path.name
        mime = _guess_mime(filename)
    return await _evaluate(svc, file_bytes, mime, filename, body)


@router.post("/evaluate_product/stream")
async def evaluate_stream(
    request: Request,
    file: UploadFile | None = File(None),
    payload: str | None = Form(None),
) -> StreamingResponse:
    """SSE variant — emits stage events as they happen, ending with one
    `result` event carrying the full EvaluateResponse JSON."""
    svc = _services(request)
    body = EvaluateRequest.model_validate_json(payload) if payload else EvaluateRequest()
    upload, path = _read_input(file, body)
    if upload is not None:
        file_bytes = await upload.read()
        filename = upload.filename
        mime = upload.content_type or _guess_mime(filename)
    else:
        file_bytes = path.read_bytes()
        filename = path.name
        mime = _guess_mime(filename)

    em = EventEmitter()

    @observe(name="evaluate_product")
    async def _run() -> None:
        token = bind_emitter(em)
        try:
            try:
                await em.stage("Picking up the specimen")
                resp = await _evaluate(svc, file_bytes, mime, filename, body)
                await em.stage("Tallying the verdict")
                await em.result(resp.model_dump(mode="json"))
            except Exception as exc:  # noqa: BLE001
                await em.error(f"{type(exc).__name__}: {exc}")
        finally:
            reset_emitter(token)
            await em.close()

    asyncio.create_task(_run())

    return StreamingResponse(
        em.stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable proxy buffering
        },
    )
