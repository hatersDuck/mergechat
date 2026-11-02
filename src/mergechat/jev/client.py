"""Thin async wrapper around the JEV / TypeSafe SDK."""

from __future__ import annotations

from time import perf_counter
from typing import Any

from typesafe_sdk import AsyncTypeSafeClient, Question

from mergechat.config import Settings


class JevConfigurationError(RuntimeError):
    """Raised when JEV credentials are not configured."""


class JevClient:
    def __init__(self, settings: Settings) -> None:
        api_key = settings.jev_api_key.get_secret_value().strip()
        if not api_key:
            raise JevConfigurationError(
                "MERGECHAT_JEV_API_KEY is required to call JEV."
            )
        self._client = AsyncTypeSafeClient(
            base_url=settings.jev_base_url,
            api_key=api_key,
            model=settings.jev_model,
            timeout=settings.jev_timeout_seconds,
            compression=False,
        )

    async def system_one(
        self,
        state: Any,
        questions: dict[str, Question],
    ) -> tuple[Any, float]:
        """Call JEV and return the response plus wall-clock latency in ms."""
        started = perf_counter()
        response = await self._client.system_one(state=state, questions=questions)
        latency_ms = (perf_counter() - started) * 1000
        return response, latency_ms

    async def aclose(self) -> None:
        await self._client.aclose()
