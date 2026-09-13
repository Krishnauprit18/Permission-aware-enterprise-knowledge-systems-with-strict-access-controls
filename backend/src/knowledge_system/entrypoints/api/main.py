"""Minimal health endpoint for validating the application package scaffold."""

from fastapi import FastAPI
from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Stable, non-sensitive liveness response."""

    status: str


app = FastAPI(title="Permission-Aware Knowledge System", version="0.1.0")


@app.get("/healthz", response_model=HealthResponse)
def healthz() -> HealthResponse:
    """Report process liveness without exposing dependency or data details."""

    return HealthResponse(status="ok")
