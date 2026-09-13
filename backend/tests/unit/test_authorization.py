"""Unit tests for the fail-closed OpenFGA authorization boundary."""

import json
from collections.abc import Mapping
from typing import cast

import httpx
import pytest

from knowledge_system.adapters.authorization.catalog import (
    InMemoryResourceMetadataStore,
)
from knowledge_system.adapters.authorization.openfga import (
    OpenFGAAdapter,
    OpenFGAConfig,
)
from knowledge_system.application.ports.authorization import (
    AuthorizationUnavailable,
    ResourceMetadata,
)
from knowledge_system.domain.contracts import (
    AuthorizationOutcome,
    AuthorizationRelation,
    AuthorizedObjectId,
    PrincipalContext,
    PrincipalId,
)


class FakeFGA:
    """Small HTTP-level fake that models current relationship changes."""

    def __init__(self) -> None:
        self.available = True
        self.resource_tenant_allowed = True
        self.calls: list[Mapping[str, object]] = []
        self.decisions: dict[tuple[str, str, str], bool] = {
            (
                "user:alice-account-manager",
                "can_view",
                "resource:acme-roadmap",
            ): True,
            (
                "user:miguel-support-engineer",
                "can_view",
                "resource:cedar-runbook",
            ): True,
            (
                "user:leah-legal-counsel",
                "restricted_viewer",
                "resource:legal-matter",
            ): True,
        }
        self.objects = [
            "resource:acme-roadmap",
            "resource:cedar-runbook",
            "resource:legal-matter",
            "resource:harbor-contract",
        ]

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if not self.available:
            return httpx.Response(503, request=request)
        payload = cast(dict[str, object], json.loads(request.content))
        self.calls.append(payload)
        if request.url.path.endswith("/check"):
            tuple_key = cast(dict[str, object], payload["tuple_key"])
            user = str(tuple_key["user"])
            relation = str(tuple_key["relation"])
            object_ref = str(tuple_key["object"])
            if relation == "member":
                allowed = (
                    object_ref == "tenant:northstar" and user != "user:harbor-user"
                )
            elif relation == "tenant":
                allowed = (
                    self.resource_tenant_allowed
                    and user == "tenant:northstar"
                    and object_ref != "resource:harbor-contract"
                )
            else:
                allowed = self.decisions.get((user, relation, object_ref), False)
            return httpx.Response(200, json={"allowed": allowed}, request=request)
        if request.url.path.endswith("/list-objects"):
            return httpx.Response(200, json={"objects": self.objects}, request=request)
        return httpx.Response(404, request=request)


class AuditSink:
    def __init__(self) -> None:
        self.records: list[dict[str, str]] = []

    def record_authorization_decision(
        self,
        decision: object,
        *,
        principal: PrincipalContext,
        object_id: AuthorizedObjectId | None,
        attributes: Mapping[str, str],
    ) -> None:
        del decision, principal, object_id
        self.records.append(dict(attributes))


def resources() -> InMemoryResourceMetadataStore:
    return InMemoryResourceMetadataStore(
        [
            ResourceMetadata(
                AuthorizedObjectId("resource:acme-roadmap"),
                "northstar",
                "INTERNAL",
                account_id="acme",
            ),
            ResourceMetadata(
                AuthorizedObjectId("resource:beacon-ticket"),
                "northstar",
                "CUSTOMER_SHAREABLE",
                account_id="beacon",
                external_shareable=True,
            ),
            ResourceMetadata(
                AuthorizedObjectId("resource:cedar-runbook"),
                "northstar",
                "INTERNAL",
                department_id="engineering",
            ),
            ResourceMetadata(
                AuthorizedObjectId("resource:legal-matter"),
                "northstar",
                "RESTRICTED",
                department_id="legal",
                restricted=True,
            ),
            ResourceMetadata(
                AuthorizedObjectId("resource:harbor-contract"),
                "harbor-labs",
                "CONFIDENTIAL",
                account_id="harbor",
            ),
        ]
    )


def principal(subject: str, tenant: str = "northstar") -> PrincipalContext:
    return PrincipalContext(
        subject_id=PrincipalId(subject),
        tenant_id=tenant,
        groups=("untrusted-claim-group",),
        correlation_id="request-123",
    )


def adapter(
    fake: FakeFGA,
    audit: AuditSink | None = None,
) -> OpenFGAAdapter:
    client = httpx.Client(transport=httpx.MockTransport(fake))
    return OpenFGAAdapter(
        OpenFGAConfig(
            base_url="http://localhost:8081",
            store_id="store-1",
            authorization_model_id="model-1",
        ),
        resources(),
        client=client,
        audit_sink=audit,
    )


@pytest.mark.unit
@pytest.mark.security
@pytest.mark.parametrize(
    ("subject", "relation", "object_id", "expected"),
    [
        (
            "alice-account-manager",
            "can_view",
            "resource:acme-roadmap",
            True,
        ),
        (
            "alice-account-manager",
            "can_view",
            "resource:beacon-ticket",
            False,
        ),
        (
            "priya-product-manager",
            "can_view",
            "resource:legal-matter",
            False,
        ),
        (
            "miguel-support-engineer",
            "can_view",
            "resource:cedar-runbook",
            True,
        ),
        (
            "leah-legal-counsel",
            "can_view",
            "resource:legal-matter",
            True,
        ),
    ],
)
def test_relationship_matrix(
    subject: str,
    relation: AuthorizationRelation,
    object_id: str,
    expected: bool,
) -> None:
    fake = FakeFGA()
    decision = adapter(fake).check(
        principal(subject), relation, AuthorizedObjectId(object_id)
    )
    assert decision.allowed is expected
    assert decision.outcome is (
        AuthorizationOutcome.ALLOW if expected else AuthorizationOutcome.DENY
    )


@pytest.mark.unit
@pytest.mark.security
def test_direct_grant_and_audit_fingerprint_are_safe() -> None:
    fake = FakeFGA()
    audit = AuditSink()
    decision = adapter(fake, audit).check(
        principal("leah-legal-counsel"),
        "can_view",
        AuthorizedObjectId("resource:legal-matter"),
    )

    assert decision.allowed is True
    assert len(decision.decision_fingerprint) == 64
    assert audit.records[0]["action"] == "can_view"
    assert audit.records[0]["authorization_model_id"] == "model-1"
    assert "legal-matter" not in audit.records[0]["reason_code"]


@pytest.mark.unit
@pytest.mark.security
def test_revoked_relation_is_denied_on_next_request() -> None:
    fake = FakeFGA()
    service = adapter(fake)
    object_id = AuthorizedObjectId("resource:acme-roadmap")

    assert service.check(
        principal("alice-account-manager"), "can_view", object_id
    ).allowed
    fake.decisions[
        ("user:alice-account-manager", "can_view", "resource:acme-roadmap")
    ] = False
    decision = service.check(principal("alice-account-manager"), "can_view", object_id)

    assert decision.allowed is False
    assert len(fake.calls) == 6


@pytest.mark.unit
@pytest.mark.security
def test_unknown_resource_is_denied_without_calling_openfga() -> None:
    fake = FakeFGA()
    decision = adapter(fake).check(
        principal("alice-account-manager"),
        "can_view",
        AuthorizedObjectId("resource:does-not-exist"),
    )

    assert decision.allowed is False
    assert decision.reason_code == "unknown_resource"
    assert fake.calls == []


@pytest.mark.unit
@pytest.mark.security
def test_tenant_isolation_is_enforced_before_relationship_allow() -> None:
    fake = FakeFGA()
    fake.decisions[("user:harbor-user", "can_view", "resource:acme-roadmap")] = True
    decision = adapter(fake).check(
        principal("harbor-user", tenant="harbor-labs"),
        "can_view",
        AuthorizedObjectId("resource:acme-roadmap"),
    )

    assert decision.allowed is False
    assert decision.reason_code == "tenant_mismatch"
    assert fake.calls == []


@pytest.mark.unit
@pytest.mark.security
def test_resource_tenant_relationship_is_required() -> None:
    fake = FakeFGA()
    fake.resource_tenant_allowed = False
    decision = adapter(fake).check(
        principal("alice-account-manager"),
        "can_view",
        AuthorizedObjectId("resource:acme-roadmap"),
    )

    assert decision.allowed is False
    assert decision.reason_code == "resource_tenant_denied"


@pytest.mark.unit
@pytest.mark.security
def test_authorizer_unavailable_fails_closed() -> None:
    fake = FakeFGA()
    fake.available = False
    service = adapter(fake)
    decision = service.check(
        principal("alice-account-manager"),
        "can_view",
        AuthorizedObjectId("resource:acme-roadmap"),
    )

    assert decision.allowed is False
    assert decision.outcome is AuthorizationOutcome.INDETERMINATE
    with pytest.raises(AuthorizationUnavailable):
        service.list_authorized_resource_ids(principal("alice-account-manager"))


@pytest.mark.unit
@pytest.mark.security
def test_list_scope_is_tenant_bound_and_rechecks_restricted_resources() -> None:
    fake = FakeFGA()
    fake.objects = ["resource:legal-matter", "resource:harbor-contract"]
    fake.decisions[
        (
            "user:leah-legal-counsel",
            "can_view",
            "resource:legal-matter",
        )
    ] = False
    scope = adapter(fake).list_authorized_resource_ids(principal("leah-legal-counsel"))

    assert scope.tenant_id == "northstar"
    assert scope.resource_ids == (AuthorizedObjectId("resource:legal-matter"),)
    assert scope.authorization_model_id == "model-1"
    assert len(scope.decision_fingerprint) == 64


@pytest.mark.unit
@pytest.mark.security
def test_external_share_requires_metadata_and_separate_fga_relation() -> None:
    fake = FakeFGA()
    fake.decisions[
        (
            "user:alice-account-manager",
            "can_share_externally",
            "resource:beacon-ticket",
        )
    ] = True
    decision = adapter(fake).check(
        principal("alice-account-manager"),
        "can_share_externally",
        AuthorizedObjectId("resource:beacon-ticket"),
    )

    assert decision.allowed is True
    assert decision.can_share_externally is True
