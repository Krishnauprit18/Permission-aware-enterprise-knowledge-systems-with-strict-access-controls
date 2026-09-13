"""HTTP-level authentication contract regressions."""

import asyncio
from dataclasses import dataclass
from time import time

import httpx
import pytest

from knowledge_system.application.authentication import (
    AuthenticationService,
    InMemorySessionRevocationStore,
)
from knowledge_system.application.ports.authentication import ValidatedIdentity
from knowledge_system.domain.contracts import PrincipalContext, PrincipalId
from knowledge_system.entrypoints.api.main import app


@dataclass(slots=True)
class StaticValidator:
    identity: ValidatedIdentity

    def validate(self, bearer_token: str, *, correlation_id: str) -> ValidatedIdentity:
        del bearer_token, correlation_id
        return self.identity


@pytest.fixture
def configured_authentication() -> None:
    identity = ValidatedIdentity(
        principal=PrincipalContext(
            subject_id=PrincipalId("alice-subject"),
            tenant_id="northstar",
            groups=("sales-customer-success",),
        ),
        session_id="session-1",
        expires_at=int(time()) + 300,
    )
    app.state.authentication_service = AuthenticationService(
        StaticValidator(identity), InMemorySessionRevocationStore()
    )


def request(
    method: str,
    path: str,
    *,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    async def send_request() -> httpx.Response:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            return await client.request(method, path, headers=headers)

    return asyncio.run(send_request())


@pytest.mark.integration
@pytest.mark.security
def test_missing_bearer_token_is_generic_and_correlated(
    configured_authentication: None,
) -> None:
    del configured_authentication
    response = request("GET", "/api/v1/auth/me")
    assert response.status_code == 401
    assert response.json() == {
        "detail": "authentication required",
    }
    assert response.headers["X-Correlation-ID"]


@pytest.mark.integration
@pytest.mark.security
def test_valid_identity_is_returned_without_token_material(
    configured_authentication: None,
) -> None:
    del configured_authentication
    response = request(
        "GET",
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer synthetic-token"},
    )
    assert response.status_code == 200
    assert response.json() == {
        "subject_id": "alice-subject",
        "tenant_id": "northstar",
        "groups": ["sales-customer-success"],
    }
    assert "synthetic-token" not in response.text


@pytest.mark.integration
@pytest.mark.security
def test_logout_then_reuse_is_rejected(configured_authentication: None) -> None:
    del configured_authentication
    logout_response = request(
        "POST",
        "/api/v1/auth/logout",
        headers={"Authorization": "Bearer synthetic-token"},
    )
    assert logout_response.status_code == 200
    assert logout_response.json() == {"status": "logged_out"}

    response = request(
        "GET",
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer synthetic-token"},
    )
    assert response.status_code == 401
    assert response.json() == {"detail": "authentication required"}
