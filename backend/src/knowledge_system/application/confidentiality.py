"""Confidentiality policy selection before grounded generation."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field, replace

from knowledge_system.application.generation import GroundedGenerationService
from knowledge_system.application.ports.authorization import (
    AuthorizationPort,
    AuthorizationUnavailable,
)
from knowledge_system.domain.contracts import (
    AuthorizationOutcome,
    AuthorizedObjectId,
    PrincipalContext,
)
from knowledge_system.domain.evidence import (
    EvidencePacket,
    EvidenceResolution,
    EvidenceSourceGroup,
)
from knowledge_system.domain.generation import GroundedAnswer
from knowledge_system.domain.policy import (
    AnswerMode,
    ConfidentialityPolicy,
    PolicyStatus,
    PolicyWarning,
    PolicyWarningCode,
    PolicyWarningSeverity,
    ShareabilityMetadata,
)


class ConfidentialityPolicyUnavailable(RuntimeError):
    """The protected share policy could not be established."""


@dataclass(frozen=True, slots=True)
class PolicySelection:
    """The only evidence package permitted for the selected answer mode."""

    mode: AnswerMode
    status: PolicyStatus
    warnings: tuple[PolicyWarning, ...]
    resolution: EvidenceResolution


@dataclass(frozen=True, slots=True)
class ConfidentialityPolicyService:
    """Apply view/share separation without asking a model to redact content."""

    authorization: AuthorizationPort
    policy: ConfidentialityPolicy = field(default_factory=ConfidentialityPolicy)

    def select(
        self,
        principal: PrincipalContext,
        mode: AnswerMode,
        resolution: EvidenceResolution,
    ) -> PolicySelection:
        if resolution.trace.correlation_id != principal.correlation_id:
            raise ConfidentialityPolicyUnavailable("policy correlation mismatch")
        if mode is AnswerMode.INTERNAL:
            warnings = self._internal_warnings(resolution.packets)
            status = (
                PolicyStatus.ALLOW_WITH_WARNINGS if warnings else PolicyStatus.ALLOW
            )
            return PolicySelection(mode, status, warnings, resolution)

        selected = []
        excluded = False
        for packet in resolution.packets:
            decision = self.policy.evaluate_external(
                ShareabilityMetadata(packet.classification, packet.external_shareable)
            )
            if not decision.allowed:
                excluded = True
                continue
            try:
                share_decision = self.authorization.check(
                    principal,
                    "can_share_externally",
                    AuthorizedObjectId(packet.document_id),
                )
            except AuthorizationUnavailable as exc:
                raise ConfidentialityPolicyUnavailable(
                    "external sharing policy unavailable"
                ) from exc
            if (
                share_decision.outcome is not AuthorizationOutcome.ALLOW
                or not share_decision.allowed
                or not share_decision.can_share_externally
            ):
                excluded = True
                continue
            selected.append(packet)

        filtered = self._filtered_resolution(resolution, selected)
        if not selected:
            return PolicySelection(
                mode,
                PolicyStatus.REFUSED,
                (
                    PolicyWarning(
                        PolicyWarningCode.CUSTOMER_SAFE_INSUFFICIENT_EVIDENCE,
                        PolicyWarningSeverity.WARNING,
                        "I do not have enough evidence to prepare a customer-safe answer.",
                    ),
                ),
                filtered,
            )
        warnings = (
            (
                PolicyWarning(
                    PolicyWarningCode.CUSTOMER_SAFE_POLICY_APPLIED,
                    PolicyWarningSeverity.INFO,
                    "Customer-safe sharing policy was applied to this answer.",
                ),
            )
            if excluded
            else ()
        )
        return PolicySelection(
            mode,
            PolicyStatus.FILTERED if excluded else PolicyStatus.ALLOW,
            warnings,
            filtered,
        )

    def _internal_warnings(
        self, packets: Sequence[EvidencePacket]
    ) -> tuple[PolicyWarning, ...]:
        warnings: list[PolicyWarning] = []
        seen: set[PolicyWarningCode] = set()
        for packet in packets:
            metadata = ShareabilityMetadata(
                packet.classification,
                packet.external_shareable,
            )
            for warning in self.policy.internal_warnings(metadata):
                if warning.code not in seen:
                    seen.add(warning.code)
                    warnings.append(warning)
        return tuple(warnings)

    @staticmethod
    def _filtered_resolution(
        resolution: EvidenceResolution,
        packets: Sequence[EvidencePacket],
    ) -> EvidenceResolution:
        selected = tuple(packets)
        selected_ids = {packet.evidence_id for packet in selected}
        groups = tuple(
            EvidenceSourceGroup(
                document_id=group.document_id,
                document_version_id=group.document_version_id,
                evidence_ids=tuple(
                    evidence_id
                    for evidence_id in group.evidence_ids
                    if evidence_id in selected_ids
                ),
            )
            for group in resolution.source_groups
            if any(evidence_id in selected_ids for evidence_id in group.evidence_ids)
        )
        conflicts = tuple(
            conflict
            for conflict in resolution.conflicts
            if set(conflict.evidence_ids).issubset(selected_ids)
        )
        relevant = (
            resolution.most_relevant_evidence_id
            if resolution.most_relevant_evidence_id in selected_ids
            else (selected[0].evidence_id if selected else None)
        )
        authoritative = (
            resolution.most_authoritative_evidence_id
            if resolution.most_authoritative_evidence_id in selected_ids
            else (selected[0].evidence_id if selected else None)
        )
        return replace(
            resolution,
            packets=selected,
            source_groups=groups,
            conflicts=conflicts,
            most_relevant_evidence_id=relevant,
            most_authoritative_evidence_id=authoritative,
        )


@dataclass(slots=True)
class PolicyAwareGenerationService:
    """Apply confidentiality selection, then delegate only the safe package."""

    policy: ConfidentialityPolicyService
    generation: GroundedGenerationService

    def answer(
        self,
        principal: PrincipalContext,
        question: str,
        resolution: EvidenceResolution,
        *,
        mode: AnswerMode = AnswerMode.INTERNAL,
    ) -> GroundedAnswer:
        try:
            selection = self.policy.select(principal, mode, resolution)
        except ConfidentialityPolicyUnavailable:
            return self.generation.policy_unavailable(
                mode=mode,
                warning=PolicyWarning(
                    PolicyWarningCode.POLICY_UNAVAILABLE,
                    PolicyWarningSeverity.ERROR,
                    "The answer service is temporarily unavailable.",
                ),
            )
        generated = self.generation.answer(
            principal,
            question,
            selection.resolution,
        )
        return replace(
            generated,
            answer_mode=selection.mode,
            policy_status=selection.status,
            policy_warnings=selection.warnings,
        )
