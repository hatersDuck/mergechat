"""FastAPI dependency helpers."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from mergechat.config import Settings
from mergechat.connectors.registry import ConnectorRegistry
from mergechat.processing.classifier import ClassifierService


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    factory = request.app.state.session_factory
    async with factory() as session:
        yield session


def get_registry(request: Request) -> ConnectorRegistry:
    return request.app.state.registry


def get_classifier(request: Request) -> ClassifierService:
    return request.app.state.classifier


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings
