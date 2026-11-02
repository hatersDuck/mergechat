"""Application entry point for MergeChat."""

from __future__ import annotations

import uvicorn

from mergechat.config import get_settings


def main() -> None:
    """Start the MergeChat API server."""
    settings = get_settings()
    uvicorn.run(
        "mergechat.api.app:create_app",
        factory=True,
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.api_reload,
        log_level=settings.log_level.lower(),
    )
