"""HTTP adapter for the local OpenFGA relationship decision service."""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
from time import monotonic
from typing import Final, cast
from urllib.parse import urlparse

import httpx

from knowledge_system.application.ports.authorization import (
    AuthorizationDecisionAuditSink,
    AuthorizationPort,
    AuthorizationScope,
    AuthorizationUnavailable,
    ResourceMetadata,
    ResourceMetadataStore,
)
from knowledge_system.domain.contracts import (
    AuthorizationDecision,
    AuthorizationOutcome,
    AuthorizationRelation,
    AuthorizedObjectId,
    PrincipalContext,
)


class OpenFGAConfigurationError(ValueError):
    """OpenFGA adapter configuration is incomplete or unsafe."""


class OpenFGAUnavailable(RuntimeError):
    """OpenFGA could not establish a relationship decision."""


@dataclass(frozen=True, slots=True)
class OpenFGAConfig:
    """Explicit local OpenFGA policy and request bounds."""

    base_url: str
    store_id: str
    authorization_model_id: str
    tuple_version: str = "tuples-v1"
    policy_version: str = "policy-v1"
    timeout_seconds: float = 0.5

    def __post_init__(self) -> None:
        parsed = urlparse(self.base_url)
        local_hosts = {"localhost", "127.0.0.1", "::1"}
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise OpenFGAConfigurationError("base URL must be absolute HTTP(S)")
        if parsed.scheme == "http" and parsed.hostname not in local_hosts:
            raise OpenFGAConfigurationError("HTTP OpenFGA is restricted to local hosts")
        if any(
            not value.strip()
            for value in (
                self.store_id,
                self.authorization_model_id,
                self.tuple_version,
                self.policy_version,
            )
        ):
            raise OpenFGAConfigurationError("OpenFGA identifiers must not be empty")
        if not 0.01 <= self.timeout_seconds <= 10:
            raise OpenFGAConfigurationError("OpenFGA timeout must be 0.01-10 seconds")


class OpenFGAAdapter(AuthorizationPort):
    """Fail-closed OpenFGA adapter with server-owned metadata enforcement."""

    _RELATIONS: Final[frozenset[str]] = frozenset({"can_view", "can_share_externally"})
    _SHAREABLE_CLASSIFICATIONS: Final[frozenset[str]] = frozenset(
        {"PUBLIC", "CUSTOMER_SHAREABLE"}
    )

    def __init__(
        self,
        config: OpenFGAConfig,
        resources: ResourceMetadataStore,
        *,
        client: httpx.Client | None = None,
        audit_sink: AuthorizationDecisionAuditSink | None = None,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self._config = config
        self._resources = resources
        self._client = client or httpx.Client(
            follow_redirects=False,
            timeout=config.timeout_seconds,
        )
        self._audit_sink = audit_sink
        self._clock = clock

    def close(self) -> None:
        """Close the adapter-owned HTTP connection pool."""

        self._client.close()

    def check(
        self,
        principal: PrincipalContext,
        relation: AuthorizationRelation,
        object_id: AuthorizedObjectId,
    ) -> AuthorizationDecision:
        started = self._clock()
        metadata = self._resources.get(object_id)
        if metadata is None:
            return self._decision(
                principal,
                relation,
                object_id,
                allowed=False,
                outcome=AuthorizationOutcome.DENY,
                reason_code="unknown_resource",
                started=started,
            )
        if metadata.tenant_id != principal.tenant_id:
            return self._decision(
                principal,
                relation,
                object_id,
                allowed=False,
                outcome=AuthorizationOutcome.DENY,
                reason_code="tenant_mismatch",
                started=started,
            )
        if relation not in self._RELATIONS:
            return self._decision(
                principal,
                relation,
                object_id,
                allowed=False,
                outcome=AuthorizationOutcome.DENY,
                reason_code="unsupported_relation",
                started=started,
            )
        if relation == "can_share_externally" and not self._shareable(metadata):
            return self._decision(
                principal,
                relation,
                object_id,
                allowed=False,
                outcome=AuthorizationOutcome.DENY,
                reason_code="classification_not_shareable",
                started=started,
            )

        try:
            tenant_member = self._check_fga(
                user=self._user_ref(principal),
                relation="member",
                object_ref=f"tenant:{principal.tenant_id}",
            )
            if not tenant_member:
                return self._decision(
                    principal,
                    relation,
                    object_id,
                    allowed=False,
                    outcome=AuthorizationOutcome.DENY,
                    reason_code="tenant_membership_denied",
                    started=started,
                )
            resource_in_tenant = self._check_fga(
                user=f"tenant:{principal.tenant_id}",
                relation="tenant",
                object_ref=str(object_id),
            )
            if not resource_in_tenant:
                return self._decision(
                    principal,
                    relation,
                    object_id,
                    allowed=False,
                    outcome=AuthorizationOutcome.DENY,
                    reason_code="resource_tenant_denied",
                    started=started,
                )
            fga_relation = "restricted_viewer" if metadata.restricted else relation
            allowed = self._check_fga(
                user=self._user_ref(principal),
                relation=fga_relation,
                object_ref=str(object_id),
            )
        except (OpenFGAUnavailable, httpx.HTTPError):
            return self._decision(
                principal,
                relation,
                object_id,
                allowed=False,
                outcome=AuthorizationOutcome.INDETERMINATE,
                reason_code="authorizer_unavailable",
                started=started,
            )
        return self._decision(
            principal,
            relation,
            object_id,
            allowed=allowed,
            outcome=(
                AuthorizationOutcome.ALLOW if allowed else AuthorizationOutcome.DENY
            ),
            reason_code="allowed" if allowed else "relation_denied",
            started=started,
        )

    def list_authorized_resource_ids(
        self,
        principal: PrincipalContext,
        relation: AuthorizationRelation = "can_view",
    ) -> AuthorizationScope:
        if relation not in self._RELATIONS:
            raise ValueError("unsupported authorization relation")
        try:
            if not self._check_fga(
                user=self._user_ref(principal),
                relation="member",
                object_ref=f"tenant:{principal.tenant_id}",
            ):
                return self._scope(principal, relation, ())
            objects = self._list_objects(
                user=self._user_ref(principal),
                relation=relation,
            )
        except (OpenFGAUnavailable, httpx.HTTPError) as exc:
            raise AuthorizationUnavailable from exc

        allowed: list[AuthorizedObjectId] = []
        try:
            for object_ref in sorted(objects):
                object_id = AuthorizedObjectId(object_ref)
                metadata = self._resources.get(object_id)
                if metadata is None or metadata.tenant_id != principal.tenant_id:
                    continue
                if not self._check_fga(
                    user=f"tenant:{principal.tenant_id}",
                    relation="tenant",
                    object_ref=object_ref,
                ):
                    continue
                if relation == "can_share_externally" and not self._shareable(metadata):
                    continue
                if metadata.restricted and relation == "can_view":
                    decision = self.check(principal, relation, object_id)
                    if not decision.allowed:
                        continue
                allowed.append(object_id)
        except (OpenFGAUnavailable, httpx.HTTPError) as exc:
            raise AuthorizationUnavailable from exc
        return self._scope(principal, relation, tuple(allowed))

    def _check_fga(self, *, user: str, relation: str, object_ref: str) -> bool:
        body = {
            "authorization_model_id": self._config.authorization_model_id,
            "consistency": "HIGHER_CONSISTENCY",
            "tuple_key": {"user": user, "relation": relation, "object": object_ref},
        }
        response = self._post(f"/stores/{self._config.store_id}/check", body)
        allowed = response.get("allowed")
        if not isinstance(allowed, bool):
            raise OpenFGAUnavailable("OpenFGA check response was incomplete")
        return allowed

    def _list_objects(self, *, user: str, relation: str) -> tuple[str, ...]:
        body = {
            "authorization_model_id": self._config.authorization_model_id,
            "user": user,
            "relation": relation,
            "type": "resource",
        }
        response = self._post(f"/stores/{self._config.store_id}/list-objects", body)
        objects = response.get("objects")
        if not isinstance(objects, list) or any(
            not isinstance(item, str) or not item.startswith("resource:")
            for item in objects
        ):
            raise OpenFGAUnavailable("OpenFGA list response was incomplete")
        return tuple(objects)

    def _post(self, path: str, body: Mapping[str, object]) -> Mapping[str, object]:
        try:
            response = self._client.post(
                f"{self._config.base_url.rstrip('/')}{path}",
                json=body,
                timeout=self._config.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise OpenFGAUnavailable from exc
        if not isinstance(payload, dict):
            raise OpenFGAUnavailable("OpenFGA response was not an object")
        return cast(Mapping[str, object], payload)

    def _decision(
        self,
        principal: PrincipalContext,
        relation: str,
        object_id: AuthorizedObjectId,
        *,
        allowed: bool,
        outcome: AuthorizationOutcome,
        reason_code: str,
        started: float,
    ) -> AuthorizationDecision:
        decision = AuthorizationDecision(
            allowed=allowed,
            can_share_externally=relation == "can_share_externally" and allowed,
            outcome=outcome,
            reason_code=reason_code,
            authorization_model_id=self._config.authorization_model_id,
            tuple_version=self._config.tuple_version,
            policy_version=self._config.policy_version,
            decision_fingerprint=self._fingerprint(
                principal, relation, object_id, outcome
            ),
            correlation_id=principal.correlation_id,
        )
        if self._audit_sink is not None:
            self._audit_sink.record_authorization_decision(
                decision,
                principal=principal,
                object_id=object_id,
                attributes={
                    "action": relation,
                    "outcome": outcome.value,
                    "reason_code": reason_code,
                    "authorization_model_id": self._config.authorization_model_id,
                    "tuple_version": self._config.tuple_version,
                    "policy_version": self._config.policy_version,
                    "duration_ms": str(int((self._clock() - started) * 1000)),
                },
            )
        return decision

    def _scope(
        self,
        principal: PrincipalContext,
        relation: AuthorizationRelation,
        resource_ids: Sequence[AuthorizedObjectId],
    ) -> AuthorizationScope:
        material = "|".join(
            (
                str(principal.subject_id),
                principal.tenant_id,
                relation,
                self._config.authorization_model_id,
                self._config.tuple_version,
                self._config.policy_version,
                *map(str, resource_ids),
            )
        )
        return AuthorizationScope(
            tenant_id=principal.tenant_id,
            relation=relation,
            resource_ids=tuple(resource_ids),
            authorization_model_id=self._config.authorization_model_id,
            tuple_version=self._config.tuple_version,
            policy_version=self._config.policy_version,
            decision_fingerprint=sha256(material.encode("utf-8")).hexdigest(),
        )

    def _fingerprint(
        self,
        principal: PrincipalContext,
        relation: str,
        object_id: AuthorizedObjectId,
        outcome: AuthorizationOutcome,
    ) -> str:
        material = "|".join(
            (
                str(principal.subject_id),
                principal.tenant_id,
                relation,
                str(object_id),
                outcome.value,
                self._config.authorization_model_id,
                self._config.tuple_version,
                self._config.policy_version,
            )
        )
        return sha256(material.encode("utf-8")).hexdigest()

    @staticmethod
    def _user_ref(principal: PrincipalContext) -> str:
        return f"user:{principal.subject_id}"

    @classmethod
    def _shareable(cls, metadata: ResourceMetadata) -> bool:
        return (
            metadata.external_shareable
            and metadata.classification in cls._SHAREABLE_CLASSIFICATIONS
        )
