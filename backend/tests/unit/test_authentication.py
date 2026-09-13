"""Authentication validation and session invalidation regressions."""

from collections.abc import Mapping
from typing import cast

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric.rsa import (
    RSAPrivateKey,
    generate_private_key,
)
from jwt import PyJWKClient

from knowledge_system.adapters.auth.logging import safe_auth_log_fields
from knowledge_system.adapters.auth.oidc import OIDCValidator, OIDCValidatorConfig
from knowledge_system.application.authentication import (
    AuthenticationFailure,
    AuthenticationService,
    InMemorySessionRevocationStore,
)
from knowledge_system.application.ports.authentication import (
    ValidatedIdentity,
)
from knowledge_system.domain.contracts import PrincipalContext, PrincipalId


class FakeSigningKey:
    def __init__(self, key: RSAPrivateKey) -> None:
        self.key = key.public_key()


class FakeJwksClient:
    def __init__(self, key: RSAPrivateKey) -> None:
        self._signing_key = FakeSigningKey(key)

    def get_signing_key_from_jwt(self, token: str) -> FakeSigningKey:
        del token
        return self._signing_key


class StaticValidator:
    def __init__(self, identity: ValidatedIdentity) -> None:
        self.identity = identity

    def validate(self, bearer_token: str, *, correlation_id: str) -> ValidatedIdentity:
        del bearer_token, correlation_id
        return self.identity


def make_token(
    key: RSAPrivateKey,
    **overrides: object,
) -> str:
    claims: dict[str, object] = {
        "iss": "http://localhost:8080/realms/knowledge-local",
        "aud": "knowledge-api-local",
        "sub": "alice-subject",
        "tenant_id": "northstar",
        "groups": ["sales-customer-success"],
        "sid": "session-1",
        "jti": "token-1",
        "iat": 1_000,
        "nbf": 1_000,
        "exp": 1_300,
    }
    claims.update(overrides)
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": "demo-key"})


@pytest.fixture
def private_key() -> RSAPrivateKey:
    return generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def validator(private_key: RSAPrivateKey) -> OIDCValidator:
    config = OIDCValidatorConfig(
        issuer="http://localhost:8080/realms/knowledge-local",
        audience="knowledge-api-local",
        clock_skew_seconds=0,
    )
    return OIDCValidator(
        config,
        jwks_client=cast(PyJWKClient, FakeJwksClient(private_key)),
        clock=lambda: 1_100.0,
    )


@pytest.mark.unit
@pytest.mark.security
def test_happy_login_builds_validated_principal(
    private_key: RSAPrivateKey, validator: OIDCValidator
) -> None:
    identity = validator.validate(make_token(private_key), correlation_id="request-1")
    assert identity.principal.subject_id == PrincipalId("alice-subject")
    assert identity.principal.tenant_id == "northstar"
    assert identity.principal.groups == ("sales-customer-success",)
    assert identity.session_id == "session-1"


@pytest.mark.unit
@pytest.mark.security
def test_missing_token_is_rejected() -> None:
    identity = ValidatedIdentity(
        PrincipalContext(PrincipalId("subject"), "northstar"), "session", 2_000_000_000
    )
    service = AuthenticationService(
        StaticValidator(identity), InMemorySessionRevocationStore()
    )
    with pytest.raises(AuthenticationFailure):
        service.authenticate(" ", correlation_id="request-1")


@pytest.mark.unit
@pytest.mark.security
@pytest.mark.parametrize(
    "overrides",
    [
        {"exp": 1_099},
        {"iss": "http://localhost:8080/realms/wrong"},
        {"aud": "another-api"},
    ],
)
def test_expired_wrong_issuer_and_wrong_audience_are_rejected(
    private_key: RSAPrivateKey,
    validator: OIDCValidator,
    overrides: Mapping[str, object],
) -> None:
    with pytest.raises(ValueError, match="invalid token"):
        validator.validate(
            make_token(private_key, **dict(overrides)), correlation_id="request-1"
        )


@pytest.mark.unit
@pytest.mark.security
def test_tampered_token_is_rejected(
    private_key: RSAPrivateKey, validator: OIDCValidator
) -> None:
    token = make_token(private_key)
    tampered = f"{token[:-1]}{'a' if token[-1] != 'a' else 'b'}"
    with pytest.raises(ValueError, match="invalid token"):
        validator.validate(tampered, correlation_id="request-1")


@pytest.mark.unit
@pytest.mark.security
def test_disabled_user_is_rejected(
    private_key: RSAPrivateKey, validator: OIDCValidator
) -> None:
    with pytest.raises(ValueError, match="invalid token"):
        validator.validate(
            make_token(private_key, enabled=False), correlation_id="request-1"
        )


@pytest.mark.unit
@pytest.mark.security
def test_malformed_group_claim_is_rejected(
    private_key: RSAPrivateKey, validator: OIDCValidator
) -> None:
    with pytest.raises(ValueError, match="invalid token"):
        validator.validate(
            make_token(private_key, groups="engineering"), correlation_id="request-1"
        )


@pytest.mark.unit
@pytest.mark.security
def test_auth_log_allowlist_excludes_token_and_cookie_values() -> None:
    safe = safe_auth_log_fields(
        {
            "event": "authentication_failed",
            "outcome": "deny",
            "reason_code": "invalid_credentials",
            "correlation_id": "request-1",
            "authorization": "Bearer synthetic-token",
            "cookie": "session=synthetic-cookie",
            "token": "synthetic-token",
        }
    )
    assert safe == {
        "event": "authentication_failed",
        "outcome": "deny",
        "reason_code": "invalid_credentials",
        "correlation_id": "request-1",
    }


@pytest.mark.unit
@pytest.mark.security
def test_logout_invalidates_the_session() -> None:
    identity = ValidatedIdentity(
        PrincipalContext(PrincipalId("subject"), "northstar"),
        "session",
        2_000_000_000,
    )
    revocations = InMemorySessionRevocationStore()
    service = AuthenticationService(StaticValidator(identity), revocations)
    service.logout("synthetic-token", correlation_id="request-1")
    with pytest.raises(AuthenticationFailure):
        service.authenticate("synthetic-token", correlation_id="request-2")
