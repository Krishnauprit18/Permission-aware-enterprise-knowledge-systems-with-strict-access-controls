"""HTTP authentication dependencies and minimal identity/session endpoints."""

import logging
import os
from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from knowledge_system.adapters.auth.logging import safe_auth_log_fields
from knowledge_system.adapters.auth.oidc import OIDCValidator, OIDCValidatorConfig
from knowledge_system.application.authentication import (
    AuthenticationFailure,
    AuthenticationService,
    InMemorySessionRevocationStore,
)
from knowledge_system.application.ports.authentication import ValidatedIdentity

logger = logging.getLogger(__name__)
bearer_scheme = HTTPBearer(auto_error=False)
router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])


class PrincipalResponse(BaseModel):
    """Safe identity response; token material is never returned."""

    subject_id: str
    tenant_id: str
    groups: tuple[str, ...]


class LogoutResponse(BaseModel):
    """Stable logout response."""

    status: str


def build_default_authentication_service() -> AuthenticationService:
    """Build the local Keycloak validator from environment configuration."""

    issuer = os.environ.get("KEYCLOAK_ISSUER_URL", "")
    audience = os.environ.get("KEYCLOAK_AUDIENCE", "knowledge-api-local")
    validator = OIDCValidator(
        OIDCValidatorConfig(
            issuer=issuer,
            audience=audience,
            clock_skew_seconds=int(os.environ.get("OIDC_CLOCK_SKEW_SECONDS", "30")),
        )
    )
    return AuthenticationService(validator, InMemorySessionRevocationStore())


def get_authentication_service(request: Request) -> AuthenticationService:
    """Use a composition-root service, allowing tests to inject a fake service."""

    service = getattr(request.app.state, "authentication_service", None)
    if service is None:
        service = build_default_authentication_service()
        request.app.state.authentication_service = service
    return cast(AuthenticationService, service)


def get_correlation_id(request: Request) -> str:
    """Read the server-generated request correlation ID."""

    return cast(str, getattr(request.state, "correlation_id", "unknown"))


async def current_identity(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),  # noqa: B008
) -> ValidatedIdentity:
    """Authenticate a request and expose only a validated identity abstraction."""

    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _authentication_required()
    try:
        return get_authentication_service(request).authenticate(
            credentials.credentials,
            correlation_id=get_correlation_id(request),
        )
    except (AuthenticationFailure, OSError, ValueError) as exc:
        logger.info(
            "authentication_failed",
            extra=safe_auth_log_fields(
                {
                    "event": "authentication_failed",
                    "outcome": "deny",
                    "reason_code": "invalid_credentials",
                    "correlation_id": get_correlation_id(request),
                }
            ),
        )
        raise _authentication_required() from exc


@router.get("/me", response_model=PrincipalResponse)
async def current_principal(
    identity: ValidatedIdentity = Depends(current_identity),  # noqa: B008
) -> PrincipalResponse:
    """Return the authenticated principal without making an authorization decision."""

    principal = identity.principal
    return PrincipalResponse(
        subject_id=str(principal.subject_id),
        tenant_id=principal.tenant_id,
        groups=principal.groups,
    )


@router.post("/logout", response_model=LogoutResponse)
async def logout(
    request: Request,
    response: Response,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),  # noqa: B008
) -> LogoutResponse:
    """Revoke the current session handle and prevent token reuse in this process."""

    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _authentication_required()
    try:
        get_authentication_service(request).logout(
            credentials.credentials,
            correlation_id=get_correlation_id(request),
        )
    except (AuthenticationFailure, OSError, ValueError) as exc:
        raise _authentication_required() from exc
    response.delete_cookie(
        "knowledge_session",
        secure=True,
        httponly=True,
        samesite="lax",
    )
    return LogoutResponse(status="logged_out")


def _authentication_required() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="authentication required",
        headers={"WWW-Authenticate": "Bearer"},
    )
