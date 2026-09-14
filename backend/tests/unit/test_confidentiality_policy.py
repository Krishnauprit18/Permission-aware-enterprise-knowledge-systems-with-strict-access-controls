"""P15 confidentiality and customer-safe generation regressions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime

import pytest

from knowledge_system.application.confidentiality import (
    ConfidentialityPolicyService,
    PolicyAwareGenerationService,
)
from knowledge_system.application.generation import GroundedGenerationService
from knowledge_system.application.ports.authorization import (
    AuthorizationScope,
    AuthorizationUnavailable,
)
from knowledge_system.domain.contracts import (
    AuthorizationDecision,
    AuthorizationOutcome,
    AuthorizationRelation,
    AuthorizedObjectId,
    EvidenceId,
    PrincipalContext,
    PrincipalId,
)
from knowledge_system.domain.evidence import (
    EvidenceAnnotation,
    EvidenceDecisionStatus,
    EvidenceFreshness,
    EvidencePacket,
    EvidenceRankDiagnostics,
    EvidenceResolution,
    EvidenceResolutionTrace,
)
from knowledge_system.domain.generation import (
    AuthorizedGenerationContext,
    CitationProposal,
    GenerationTrace,
    ModelClaim,
    ModelDraft,
)
from knowledge_system.domain.persistence import Classification
from knowledge_system.domain.policy import (
    AnswerMode,
    ConfidentialityPolicy,
    PolicyStatus,
    PolicyWarning,
    PolicyWarningCode,
    PolicyWarningSeverity,
    ShareabilityMetadata,
)

pytestmark = [pytest.mark.unit, pytest.mark.security]


def _timestamp() -> datetime:
    return datetime(2026, 9, 14, 12, 0, tzinfo=UTC)


def _principal() -> PrincipalContext:
    return PrincipalContext(
        subject_id=PrincipalId("user:maya-account-manager"),
        tenant_id="northstar",
        correlation_id="corr-p15",
    )


def _packet(
    evidence_id: str,
    text: str,
    *,
    document_id: str,
    classification: Classification,
    external_shareable: bool,
) -> EvidencePacket:
    return EvidencePacket(
        evidence_id=EvidenceId(evidence_id),
        chunk_id=f"chunk-{evidence_id}",
        document_id=document_id,
        document_version_id=f"version-{evidence_id}",
        sanitized_text=text,
        source_type="document",
        source_locator=(f"document:{evidence_id}#section=Decision",),
        source_url=f"https://source.invalid/{evidence_id}",
        updated_at=_timestamp(),
        effective_at=_timestamp(),
        authority_level=5,
        freshness=EvidenceFreshness.CURRENT,
        decision_status=EvidenceDecisionStatus.APPROVED,
        classification=classification,
        external_shareable=external_shareable,
        conflict_group=None,
        supersedes_document_ids=(),
        superseded_by_document_ids=(),
        annotations=(EvidenceAnnotation.APPROVED,),
        authorization_fingerprint="view-fingerprint",
        diagnostics=EvidenceRankDiagnostics(1, 1, 1.0, False, ("test",)),
    )


def _resolution(*packets: EvidencePacket) -> EvidenceResolution:
    return EvidenceResolution(
        packets=tuple(packets),
        source_groups=(),
        conflicts=(),
        most_relevant_evidence_id=packets[0].evidence_id if packets else None,
        most_authoritative_evidence_id=packets[0].evidence_id if packets else None,
        trace=EvidenceResolutionTrace(
            correlation_id="corr-p15",
            authorization_fingerprint="view-fingerprint",
            reranker_version="test-reranker",
            input_candidate_count=len(packets),
            reauthorized_candidate_count=len(packets),
            loaded_material_count=len(packets),
            duplicate_count=0,
            authorization_drop_count=0,
            fallback_used=False,
        ),
    )


def _draft(evidence_id: str, quote: str) -> ModelDraft:
    return ModelDraft(
        claims=(
            ModelClaim(
                text="The approved customer date is September 24.",
                citations=(CitationProposal(EvidenceId(evidence_id), quote),),
            ),
        )
    )


@dataclass
class _Authorization:
    share_decisions: Mapping[str, bool] = field(default_factory=dict)
    unavailable: bool = False
    calls: list[tuple[str, str]] = field(default_factory=list)

    def check(
        self,
        principal: PrincipalContext,
        relation: str,
        object_id: AuthorizedObjectId,
    ) -> AuthorizationDecision:
        del principal
        self.calls.append((relation, str(object_id)))
        if self.unavailable:
            raise AuthorizationUnavailable("offline")
        allowed = self.share_decisions.get(str(object_id), False)
        return AuthorizationDecision(
            allowed=allowed,
            can_share_externally=relation == "can_share_externally" and allowed,
            outcome=(
                AuthorizationOutcome.ALLOW if allowed else AuthorizationOutcome.DENY
            ),
            reason_code="test",
            decision_fingerprint=f"share-{object_id}",
            correlation_id="corr-p15",
        )

    def list_authorized_resource_ids(
        self,
        principal: PrincipalContext,
        relation: AuthorizationRelation = "can_view",
    ) -> AuthorizationScope:
        del principal, relation
        raise AssertionError("scope listing is not part of the P15 policy path")


@dataclass
class _Model:
    drafts: list[ModelDraft]
    calls: list[tuple[AuthorizedGenerationContext, bool]] = field(default_factory=list)
    model_id: str = "local-test-model"
    model_version: str = "test-v1"

    def generate(
        self, context: AuthorizedGenerationContext, *, retry: bool
    ) -> ModelDraft:
        self.calls.append((context, retry))
        return self.drafts.pop(0)


@dataclass
class _TraceSink:
    traces: list[GenerationTrace] = field(default_factory=list)

    def record(self, trace: GenerationTrace) -> None:
        self.traces.append(trace)


def _service(
    authorization: _Authorization,
    model: _Model,
) -> PolicyAwareGenerationService:
    generation = GroundedGenerationService(model, _TraceSink(), clock=_timestamp)
    return PolicyAwareGenerationService(
        ConfidentialityPolicyService(authorization), generation
    )


def test_customer_safe_excludes_viewable_product_internal_discussion() -> None:
    internal = _packet(
        "product-internal",
        "Product discussed an internal launch concern.",
        document_id="resource:product-internal",
        classification=Classification.INTERNAL,
        external_shareable=False,
    )
    model = _Model([])

    answer = _service(_Authorization(), model).answer(
        _principal(),
        "What is the launch concern?",
        _resolution(internal),
        mode=AnswerMode.CUSTOMER_SAFE,
    )

    assert answer.outcome.value == "REFUSED"
    assert answer.answer_mode is AnswerMode.CUSTOMER_SAFE
    assert answer.policy_status is PolicyStatus.REFUSED
    assert not model.calls
    assert "product-internal" not in answer.message
    assert all(
        "product-internal" not in warning.message for warning in answer.policy_warnings
    )


def test_internal_mode_preserves_authorized_evidence_and_surfaces_warning() -> None:
    internal = _packet(
        "product-internal",
        "Internal launch concern.",
        document_id="resource:product-internal",
        classification=Classification.INTERNAL,
        external_shareable=False,
    )
    model = _Model([_draft("product-internal", "Internal launch concern")])

    answer = _service(_Authorization(), model).answer(
        _principal(), "What is the launch concern?", _resolution(internal)
    )

    assert answer.outcome.value == "ANSWERED"
    assert answer.answer_mode is AnswerMode.INTERNAL
    assert answer.policy_status is PolicyStatus.ALLOW_WITH_WARNINGS
    assert answer.policy_warnings[0].code is PolicyWarningCode.INTERNAL_CONTENT_PRESENT
    context, _retry = model.calls[0]
    assert context.evidence_ids == (internal.evidence_id,)


def test_customer_safe_uses_approved_customer_shareable_source_only() -> None:
    internal = _packet(
        "product-internal",
        "Internal launch concern.",
        document_id="resource:product-internal",
        classification=Classification.INTERNAL,
        external_shareable=False,
    )
    approved = _packet(
        "customer-approved",
        "The approved customer date is September 24.",
        document_id="resource:customer-approved",
        classification=Classification.CUSTOMER_SHAREABLE,
        external_shareable=True,
    )
    model = _Model(
        [_draft("customer-approved", "approved customer date is September 24")]
    )
    authorization = _Authorization({"resource:customer-approved": True})

    answer = _service(authorization, model).answer(
        _principal(),
        "What date can we tell the customer?",
        _resolution(internal, approved),
        mode=AnswerMode.CUSTOMER_SAFE,
    )

    assert answer.outcome.value == "ANSWERED"
    assert answer.policy_status is PolicyStatus.FILTERED
    context, _retry = model.calls[0]
    assert [str(item.evidence_id) for item in context.evidence] == ["customer-approved"]
    assert "Internal launch concern." not in context.evidence_data_json()
    assert authorization.calls == [
        ("can_share_externally", "resource:customer-approved")
    ]
    assert (
        answer.policy_warnings[0].code is PolicyWarningCode.CUSTOMER_SAFE_POLICY_APPLIED
    )


def test_legal_only_inaccessible_content_does_not_leak_existence() -> None:
    model = _Model([])

    answer = _service(_Authorization(), model).answer(
        _principal(),
        "What is in Legal's matter?",
        _resolution(),
        mode=AnswerMode.CUSTOMER_SAFE,
    )

    assert answer.policy_status is PolicyStatus.REFUSED
    assert (
        answer.policy_warnings[0].code
        is PolicyWarningCode.CUSTOMER_SAFE_INSUFFICIENT_EVIDENCE
    )
    assert "legal" not in answer.message.lower()
    assert "legal" not in answer.policy_warnings[0].message.lower()
    assert not model.calls


def test_missing_shareability_metadata_denies_customer_safe_use() -> None:
    decision = ConfidentialityPolicy().evaluate_external(
        ShareabilityMetadata(classification=None, external_shareable=None)
    )

    assert not decision.allowed
    assert decision.reason_code == "missing_classification"


@pytest.mark.parametrize(
    ("classification", "external_shareable", "reason"),
    [
        (Classification.PUBLIC, None, "missing_or_false_shareability"),
        (Classification.INTERNAL, True, "classification_not_shareable"),
    ],
)
def test_external_policy_requires_explicit_shareable_classification(
    classification: Classification,
    external_shareable: bool | None,
    reason: str,
) -> None:
    decision = ConfidentialityPolicy().evaluate_external(
        ShareabilityMetadata(classification, external_shareable)
    )

    assert not decision.allowed
    assert decision.reason_code == reason


def test_external_policy_allows_public_only_when_flag_is_explicit() -> None:
    decision = ConfidentialityPolicy().evaluate_external(
        ShareabilityMetadata(Classification.PUBLIC, True)
    )

    assert decision.allowed
    assert decision.reason_code == "shareable"


@pytest.mark.parametrize(
    ("classification", "warning"),
    [
        (Classification.INTERNAL, PolicyWarningCode.INTERNAL_CONTENT_PRESENT),
        (Classification.CONFIDENTIAL, PolicyWarningCode.CONFIDENTIAL_CONTENT_PRESENT),
        (Classification.RESTRICTED, PolicyWarningCode.RESTRICTED_CONTENT_PRESENT),
        (Classification.PUBLIC, None),
    ],
)
def test_internal_warning_taxonomy_is_deterministic(
    classification: Classification,
    warning: PolicyWarningCode | None,
) -> None:
    warnings = ConfidentialityPolicy().internal_warnings(
        ShareabilityMetadata(classification, False)
    )

    assert tuple(item.code for item in warnings) == (
        () if warning is None else (warning,)
    )


def test_policy_warning_rejects_empty_or_overlong_messages() -> None:
    with pytest.raises(ValueError):
        PolicyWarning(
            PolicyWarningCode.INTERNAL_CONTENT_PRESENT,
            PolicyWarningSeverity.WARNING,
            "",
        )


def test_classification_change_applies_on_next_answer_path() -> None:
    source = _packet(
        "changing-source",
        "The approved customer date is September 24.",
        document_id="resource:changing-source",
        classification=Classification.INTERNAL,
        external_shareable=False,
    )
    authorization = _Authorization({"resource:changing-source": True})
    first_model = _Model([])
    service = _service(authorization, first_model)

    first = service.answer(
        _principal(), "What date?", _resolution(source), mode=AnswerMode.CUSTOMER_SAFE
    )
    assert first.policy_status is PolicyStatus.REFUSED
    assert not first_model.calls

    changed = replace(
        source,
        classification=Classification.CUSTOMER_SHAREABLE,
        external_shareable=True,
    )
    second_model = _Model(
        [_draft("changing-source", "approved customer date is September 24")]
    )
    second = _service(authorization, second_model).answer(
        _principal(), "What date?", _resolution(changed), mode=AnswerMode.CUSTOMER_SAFE
    )

    assert second.policy_status is PolicyStatus.ALLOW
    assert second.outcome.value == "ANSWERED"
    assert len(second_model.calls) == 1


def test_external_policy_failure_is_generic_and_model_free() -> None:
    shareable = _packet(
        "customer-approved",
        "Approved customer date.",
        document_id="resource:customer-approved",
        classification=Classification.CUSTOMER_SHAREABLE,
        external_shareable=True,
    )
    model = _Model([])

    answer = _service(_Authorization(unavailable=True), model).answer(
        _principal(),
        "What date?",
        _resolution(shareable),
        mode=AnswerMode.CUSTOMER_SAFE,
    )

    assert answer.policy_status is PolicyStatus.UNAVAILABLE
    assert answer.policy_warnings[0].code is PolicyWarningCode.POLICY_UNAVAILABLE
    assert not model.calls
