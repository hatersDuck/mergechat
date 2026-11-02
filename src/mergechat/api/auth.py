"""API authentication for non-loopback deployments."""

from __future__ import annotations

from hmac import compare_digest

from fastapi import Request
from fastapi.responses import JSONResponse

PUBLIC_PATHS = {"/", "/info", "/healthz", "/docs", "/redoc", "/openapi.json"}
PUBLIC_PREFIXES = ("/ui/",)
LOOPBACK_CLIENTS = {"127.0.0.1", "::1", "localhost", "testclient"}


def _is_public(path: str) -> bool:
    return path in PUBLIC_PATHS or path == "/ui" or path.startswith(PUBLIC_PREFIXES)


def _unauthorized(detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=401,
        content={"detail": detail},
        headers={"WWW-Authenticate": "Bearer"},
    )


async def require_api_auth(request: Request, call_next):
    """Require a bearer token, or restrict unauthenticated access to loopback."""
    if request.method == "OPTIONS" or _is_public(request.url.path):
        return await call_next(request)

    token = request.app.state.settings.api_token.get_secret_value().strip()
    if token:
        scheme, _, provided = request.headers.get("authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not compare_digest(
            provided.strip(), token
        ):
            return _unauthorized("A valid bearer token is required.")
        return await call_next(request)

    client_host = request.client.host if request.client is not None else ""
    forwarded = any(
        request.headers.get(header)
        for header in ("forwarded", "x-forwarded-for", "x-real-ip")
    )
    if client_host not in LOOPBACK_CLIENTS or forwarded:
        return _unauthorized(
            "Unauthenticated access is limited to loopback. Set "
            "MERGECHAT_API_TOKEN for remote access."
        )
    return await call_next(request)
