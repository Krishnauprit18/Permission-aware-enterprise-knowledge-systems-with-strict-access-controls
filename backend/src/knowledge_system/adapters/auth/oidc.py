"""Keycloak-compatible OIDC JWT validation with strict claim requirements."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from time import time
from typing import Final, cast
from urllib.parse import urlparse

import jwt
from jwt import PyJWKClient
from jwt.exceptions import InvalidTokenError, PyJWKClientError

from knowledge_system.application.ports.authentication import ValidatedIdentity
from knowledge_system.domain.contracts import PrincipalContext, PrincipalId


class OIDCConfigurationError(ValueError):
    """OIDC configuration is unsafe or incomplete."""


class OIDCValidationError(ValueError):
    """The presented token is not an acceptable identity assertion."""


@dataclass(frozen=True, slots=True)
class OIDCValidatorConfig:
    """Explicit validation policy; local HTTP is allowed only for local hosts."""

    issuer: str
    audience: str
    algorithms: tuple[str, ...] = ("RS256",)
    clock_skew_seconds: int = 30

    def __post_init__(self) -> None:
        parsed = urlparse(self.issuer)
        local_hosts = {"localhost", "127.0.0.1", "::1"}
        if parsed.scheme not in {"https", "http"} or not parsed.netloc:
            raise OIDCConfigurationError("issuer must be an absolute HTTP(S) URL")
        if parsed.scheme == "http" and parsed.hostname not in local_hosts:
            raise OIDCConfigurationError("HTTP issuer is restricted to local hosts")
        if not self.audience.strip():
            raise OIDCConfigurationError("audience must not be empty")
        if not self.algorithms or any(
            algorithm != "RS256" for algorithm in self.algorithms
        ):
            raise OIDCConfigurationError(
                "only the configured RS256 policy is supported"
            )
        if not 0 <= self.clock_skew_seconds <= 300:
            raise OIDCConfigurationError("clock skew must be between 0 and 300 seconds")


class OIDCValidator:
    """Validate Keycloak access tokens without retaining token material."""

    _REQUIRED_CLAIMS: Final[tuple[str, ...]] = (
        "exp",
        "iat",
        "nbf",
        "iss",
        "aud",
        "sub",
    )

    def __init__(
        self,
        config: OIDCValidatorConfig,
        *,
        jwks_client: PyJWKClient | None = None,
        clock: Callable[[], float] = time,
    ) -> None:
        self._config = config
        jwks_uri = f"{config.issuer.rstrip('/')}/protocol/openid-connect/certs"
        self._jwks_client = jwks_client or PyJWKClient(
            jwks_uri,
            cache_jwk_set=True,
            cache_keys=True,
            lifespan=300,
        )
        self._clock = clock

    def validate(self, bearer_token: str, *, correlation_id: str) -> ValidatedIdentity:
        if not bearer_token or len(bearer_token) > 16384:
            raise OIDCValidationError("invalid token")
        try:
            header = jwt.get_unverified_header(bearer_token)
            algorithm = header.get("alg")
            if algorithm not in self._config.algorithms or not header.get("kid"):
                raise OIDCValidationError("invalid token")
            signing_key = self._jwks_client.get_signing_key_from_jwt(bearer_token)
            claims = cast(
                Mapping[str, object],
                jwt.decode(
                    bearer_token,
                    signing_key.key,
                    algorithms=list(self._config.algorithms),
                    audience=self._config.audience,
                    issuer=self._config.issuer,
                    leeway=self._config.clock_skew_seconds,
                    options={
                        "require": list(self._REQUIRED_CLAIMS),
                        "verify_exp": False,
                        "verify_iat": False,
                        "verify_nbf": False,
                    },
                ),
            )
        except (
            InvalidTokenError,
            OIDCValidationError,
            PyJWKClientError,
            TypeError,
            ValueError,
        ) as exc:
            raise OIDCValidationError("invalid token") from exc

        subject = self._required_string(claims, "sub")
        tenant_id = self._required_string(claims, "tenant_id")
        expires_at = self._required_int(claims, "exp")
        not_before = self._required_int(claims, "nbf")
        issued_at = self._required_int(claims, "iat")
        now = int(self._clock())
        skew = self._config.clock_skew_seconds
        if (
            expires_at <= now - skew
            or not_before > now + skew
            or issued_at > now + skew
        ):
            raise OIDCValidationError("invalid token")
        if claims.get("enabled") is False:
            raise OIDCValidationError("invalid token")

        groups_claim = claims.get("groups", ())
        if not isinstance(groups_claim, list) or any(
            not isinstance(group, str) or not group for group in groups_claim
        ):
            raise OIDCValidationError("invalid token")
        session_id = self._optional_string(claims, "sid") or self._required_string(
            claims, "jti"
        )
        safe_claims: Mapping[str, object] = {
            "email_verified": claims.get("email_verified", False),
            "session_state": claims.get("session_state", ""),
        }
        principal = PrincipalContext(
            subject_id=PrincipalId(subject),
            tenant_id=tenant_id,
            groups=tuple(groups_claim),
            claims=safe_claims,
            correlation_id=correlation_id,
        )
        return ValidatedIdentity(
            principal=principal,
            session_id=session_id,
            expires_at=expires_at,
        )

    @staticmethod
    def _required_string(claims: Mapping[str, object], name: str) -> str:
        value = claims.get(name)
        if not isinstance(value, str) or not value:
            raise OIDCValidationError("invalid token")
        return value

    @staticmethod
    def _optional_string(claims: Mapping[str, object], name: str) -> str | None:
        value = claims.get(name)
        if value is None:
            return None
        if not isinstance(value, str) or not value:
            raise OIDCValidationError("invalid token")
        return value

    @staticmethod
    def _required_int(claims: Mapping[str, object], name: str) -> int:
        value = claims.get(name)
        if isinstance(value, bool) or not isinstance(value, int):
            raise OIDCValidationError("invalid token")
        return value
