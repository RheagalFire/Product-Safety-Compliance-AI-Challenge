from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI

load_dotenv()

import app.observability  # noqa: F401, E402  registers litellm langfuse callback at import
from app.api.router import router  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.services import Services  # noqa: E402


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
    return app


app = create_app()
