"""Typed ports for the server-side relationship authorization boundary."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from knowledge_system.domain.contracts import (
    AuthorizationDecision,
    AuthorizationRelation,
    AuthorizedObjectId,
    PrincipalContext,
)


class AuthorizationUnavailable(RuntimeError):
    """A protected authorization scope could not be established."""


@dataclass(frozen=True, slots=True)
class ResourceMetadata:
    """Trusted server metadata required before an authorization allow."""

    object_id: AuthorizedObjectId
    tenant_id: str
    classification: str
    account_id: str | None = None
    department_id: str | None = None
    restricted: bool = False
    external_shareable: bool = False


@dataclass(frozen=True, slots=True)
class AuthorizationScope:
    """Metadata-only, request-bound scope for permission-first search."""

    tenant_id: str
    relation: AuthorizationRelation
    resource_ids: tuple[AuthorizedObjectId, ...]
    authorization_model_id: str
    tuple_version: str
    policy_version: str
    decision_fingerprint: str


class ResourceMetadataStore(Protocol):
    """Reads trusted resource security metadata without returning content."""

    def get(self, object_id: AuthorizedObjectId) -> ResourceMetadata | None: ...

    def all_for_tenant(self, tenant_id: str) -> Sequence[ResourceMetadata]: ...


class AuthorizationPort(Protocol):
    """Policy enforcement point backed by current relationship truth."""

    def check(
        self,
        principal: PrincipalContext,
        relation: AuthorizationRelation,
        object_id: AuthorizedObjectId,
    ) -> AuthorizationDecision: ...

    def list_authorized_resource_ids(
        self,
        principal: PrincipalContext,
        relation: AuthorizationRelation = "can_view",
    ) -> AuthorizationScope: ...


class AuthorizationDecisionAuditSink(Protocol):
    """Receives safe decision metadata, never relationship graph contents."""

    def record_authorization_decision(
        self,
        decision: AuthorizationDecision,
        *,
        principal: PrincipalContext,
        object_id: AuthorizedObjectId | None,
        attributes: Mapping[str, str],
    ) -> None: ...
