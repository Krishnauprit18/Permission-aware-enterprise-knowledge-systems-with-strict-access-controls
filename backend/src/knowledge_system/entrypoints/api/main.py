"""API composition root for health and identity boundaries."""

from uuid import uuid4

from fastapi import FastAPI
from pydantic import BaseModel
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from knowledge_system.entrypoints.api.auth import router as auth_router


class HealthResponse(BaseModel):
    """Stable, non-sensitive liveness response."""

    status: str


app = FastAPI(title="Permission-Aware Knowledge System", version="0.1.0")
app.include_router(auth_router)


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


@app.get("/healthz", response_model=HealthResponse)
async def healthz() -> HealthResponse:
    """Report process liveness without exposing dependency or data details."""

    return HealthResponse(status="ok")
