"""API composition root for health, identity, and product boundaries."""

import os
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from knowledge_system.entrypoints.api.auth import router as auth_router
from knowledge_system.entrypoints.api.query import router as query_router


class HealthResponse(BaseModel):
    """Stable, non-sensitive liveness response."""

    status: str


app = FastAPI(title="Permission-Aware Knowledge System", version="0.1.0")
app.include_router(auth_router)
app.include_router(query_router)

_allowed_origins = tuple(
    origin.strip()
    for origin in os.environ.get(
        "KNOWLEDGE_ALLOWED_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if origin.strip()
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(_allowed_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


class CorrelationIdMiddleware:
    """Generate a fresh correlation ID without a blocking middleware bridge."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        correlation_id = str(uuid4())
        state = dict(scope.get("state", {}))
        state["correlation_id"] = correlation_id
        scoped = {**scope, "state": state}

        async def send_with_correlation(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message["headers"])
                headers.append((b"x-correlation-id", correlation_id.encode("ascii")))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scoped, receive, send_with_correlation)


app.add_middleware(CorrelationIdMiddleware)


class SecurityHeadersMiddleware:
    """Apply browser boundary headers to every HTTP response."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        async def send_with_security_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message["headers"])
                headers.extend(
                    (
                        (
                            b"content-security-policy",
                            b"default-src 'none'; frame-ancestors 'none'",
                        ),
                        (b"x-content-type-options", b"nosniff"),
                        (b"referrer-policy", b"no-referrer"),
                        (
                            b"permissions-policy",
                            b"camera=(), microphone=(), geolocation=()",
                        ),
                        (b"x-frame-options", b"DENY"),
                    )
                )
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_security_headers)


app.add_middleware(SecurityHeadersMiddleware)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Keep validation failures bounded and free of field/content echoing."""

    del exc
    return JSONResponse(
        status_code=422,
        content={
            "code": "INVALID_REQUEST",
            "message": "The request is invalid.",
            "request_id": getattr(request.state, "correlation_id", "unknown"),
        },
    )


@app.get("/healthz", response_model=HealthResponse)
async def healthz() -> HealthResponse:
    """Report process liveness without exposing dependency or data details."""

    return HealthResponse(status="ok")
