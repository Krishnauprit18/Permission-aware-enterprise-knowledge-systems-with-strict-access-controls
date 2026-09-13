"""API composition root for health and identity boundaries."""

from uuid import uuid4

from fastapi import FastAPI, Request
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from knowledge_system.entrypoints.api.auth import router as auth_router


class HealthResponse(BaseModel):
    """Stable, non-sensitive liveness response."""

    status: str


app = FastAPI(title="Permission-Aware Knowledge System", version="0.1.0")
app.include_router(auth_router)


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Generate a fresh correlation ID and never trust a client token as one."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        correlation_id = str(uuid4())
        request.state.correlation_id = correlation_id
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = correlation_id
        return response


app.add_middleware(CorrelationIdMiddleware)


@app.get("/healthz", response_model=HealthResponse)
def healthz() -> HealthResponse:
    """Report process liveness without exposing dependency or data details."""

    return HealthResponse(status="ok")
