"""Application-level JEV classification service."""

from __future__ import annotations

from mergechat.config import Settings
from mergechat.domain.message import RawMessage
from mergechat.jev.client import JevClient
from mergechat.jev.prompts import PROMPT_VERSION, build_questions, build_state
from mergechat.jev.schemas import JevClassification, parse_response


class JevService:
    def __init__(self, settings: Settings, client: JevClient | None = None) -> None:
        self._settings = settings
        self._client = client or JevClient(settings)
        self._questions = build_questions()

    @property
    def prompt_version(self) -> str:
        return PROMPT_VERSION

    async def classify(self, message: RawMessage) -> JevClassification:
        response, latency_ms = await self._client.system_one(
            state=build_state(message),
            questions=self._questions,
        )
        return parse_response(
            response,
            prompt_version=PROMPT_VERSION,
            latency_ms=latency_ms,
            threshold=self._settings.jev_confidence_threshold,
        )

    async def classify_many(
        self, messages: list[RawMessage]
    ) -> list[JevClassification]:
        return [await self.classify(message) for message in messages]

    async def aclose(self) -> None:
        await self._client.aclose()
