from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse

load_dotenv()

import app.observability  # noqa: F401, E402  registers litellm langfuse callback at import
from app.api.router import router  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.services import Services  # noqa: E402

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.settings = settings
    app.state.services = await Services.build(settings)
    try:
        yield
    finally:
        await app.state.services.aclose()
        try:
            from langfuse import get_client

            get_client().flush()
        except Exception:
            pass


def create_app() -> FastAPI:
    app = FastAPI(
        title="Product Safety Compliance",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(router)

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    return app


app = create_app()
