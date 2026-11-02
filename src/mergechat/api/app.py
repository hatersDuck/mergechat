"""FastAPI application factory."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from mergechat.api.auth import require_api_auth
from mergechat.api.routes import accounts, chats, classifications, labels, messages
from mergechat.config import Settings, get_settings
from mergechat.connectors.registry import ConnectorRegistry
from mergechat.jev.client import JevConfigurationError
from mergechat.jev.service import JevService
from mergechat.logging import configure_logging
from mergechat.processing.classifier import ClassifierService
from mergechat.processing.ingestion import IngestionService
from mergechat.storage import repositories
from mergechat.storage.database import (
    create_engine,
    create_session_factory,
    ensure_schema,
)

logger = logging.getLogger(__name__)
WEB_DIR = Path(__file__).resolve().parent.parent / "web"


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        configure_logging(app_settings.log_level)
        engine = create_engine(app_settings)
        session_factory = create_session_factory(engine)
        await ensure_schema(app_settings)
        async with session_factory() as session:
            await repositories.reset_transient_account_statuses(session)
            await session.commit()

        ingestion = IngestionService(session_factory)
        try:
            jev_service: JevService | None = JevService(app_settings)
        except JevConfigurationError:
            logger.warning("JEV is not configured; classification endpoints will fail.")
            jev_service = None

        classifier = ClassifierService(session_factory, jev_service)
        registry = ConnectorRegistry(app_settings, session_factory, ingestion)

        app.state.settings = app_settings
        app.state.engine = engine
        app.state.session_factory = session_factory
        app.state.ingestion = ingestion
        app.state.jev_service = jev_service
        app.state.classifier = classifier
        app.state.registry = registry

        logger.info("MergeChat API started")
        try:
            yield
        finally:
            await registry.stop_all()
            if jev_service is not None:
                await jev_service.aclose()
            await engine.dispose()
            logger.info("MergeChat API stopped")

    app = FastAPI(
        title="MergeChat Phase 0",
        version="0.1.0",
        description=(
            "Feasibility spike for passive Max chat monitoring and JEV order "
            "classification."
        ),
        lifespan=lifespan,
    )

    app.middleware("http")(require_api_auth)

    app.include_router(accounts.router)
    app.include_router(chats.router)
    app.include_router(messages.router)
    app.include_router(classifications.router)
    app.include_router(labels.router)

    @app.get("/healthz", tags=["system"])
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/", include_in_schema=False)
    async def root() -> RedirectResponse:
        return RedirectResponse(url="/ui/")

    @app.get("/info", tags=["system"])
    async def info() -> dict[str, str]:
        return {
            "name": "mergechat",
            "ui": "/ui/",
            "docs": "/docs",
            "health": "/healthz",
        }

    if WEB_DIR.is_dir():
        app.mount("/ui", StaticFiles(directory=WEB_DIR, html=True), name="ui")

    return app
