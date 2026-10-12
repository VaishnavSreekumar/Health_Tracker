"""HealthTrack application initialization and foundational endpoints."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Optional
from fastapi import FastAPI
from sqlalchemy import Engine

import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logging.getLogger("app").setLevel(logging.INFO)

from app.api.v1 import api_v1_router
from app.core.config import Settings, get_settings
from app.db.session import get_engine, init_db
from app.schemas.health import HealthResponse


def create_app(
    settings: Optional[Settings] = None,
    engine: Optional[Engine] = None,
    init_database: bool = True,
) -> FastAPI:
    """Application factory for HealthTrack FastAPI service.

    Args:
        settings: Optional custom Settings instance.
        engine: Optional SQLAlchemy Engine to bind to.
        init_database: Whether to initialize database tables on startup.
    """
    current_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        if init_database:
            target_engine = engine or get_engine()
            init_db(target_engine)
        yield

    app = FastAPI(
        title=current_settings.project_name,
        version=current_settings.version,
        description="AI-driven healthcare follow-up management service foundation.",
        lifespan=lifespan,
    )

    from fastapi.middleware.cors import CORSMiddleware

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", response_model=HealthResponse, tags=["System"])
    def get_health() -> HealthResponse:
        """System health and operational readiness check."""
        return HealthResponse(
            status="healthy",
            service=current_settings.project_name,
            version=current_settings.version,
            environment=current_settings.environment,
        )

    app.include_router(api_v1_router)

    import os
    from fastapi.staticfiles import StaticFiles

    dist_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "dist")
    if os.path.isdir(dist_dir):
        app.mount("/", StaticFiles(directory=dist_dir, html=True), name="frontend")

    return app


# Default ASGI application instance for uvicorn
app = create_app()
