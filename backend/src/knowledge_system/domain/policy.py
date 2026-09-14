"""Deterministic answer-mode and confidentiality policy contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from knowledge_system.domain.persistence import Classification


class AnswerMode(StrEnum):
    """Audience policy selected by the trusted application boundary."""

    INTERNAL = "INTERNAL"
    CUSTOMER_SAFE = "CUSTOMER_SAFE"


class PolicyStatus(StrEnum):
    """Machine-readable policy result safe to return with an answer."""

    ALLOW = "ALLOW"
    ALLOW_WITH_WARNINGS = "ALLOW_WITH_WARNINGS"
    FILTERED = "FILTERED"
    REFUSED = "REFUSED"
    UNAVAILABLE = "UNAVAILABLE"


class PolicyWarningCode(StrEnum):
    """Stable warning taxonomy; values contain no resource identifiers."""

    INTERNAL_CONTENT_PRESENT = "INTERNAL_CONTENT_PRESENT"
    CONFIDENTIAL_CONTENT_PRESENT = "CONFIDENTIAL_CONTENT_PRESENT"
    RESTRICTED_CONTENT_PRESENT = "RESTRICTED_CONTENT_PRESENT"
    CUSTOMER_SAFE_POLICY_APPLIED = "CUSTOMER_SAFE_POLICY_APPLIED"
    CUSTOMER_SAFE_INSUFFICIENT_EVIDENCE = "CUSTOMER_SAFE_INSUFFICIENT_EVIDENCE"
    POLICY_UNAVAILABLE = "POLICY_UNAVAILABLE"


class PolicyWarningSeverity(StrEnum):
    """Presentation severity independent of the authorization decision."""

    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


@dataclass(frozen=True, slots=True)
class PolicyWarning:
    """User-safe policy warning with no protected resource details."""

    code: PolicyWarningCode
    severity: PolicyWarningSeverity
    message: str

    def __post_init__(self) -> None:
        if not self.message.strip() or len(self.message) > 240:
            raise ValueError("policy warning message is invalid")


@dataclass(frozen=True, slots=True)
class ShareabilityMetadata:
    """Trusted policy metadata; missing values are represented explicitly."""

    classification: Classification | None
    external_shareable: bool | None


@dataclass(frozen=True, slots=True)
class ShareabilityDecision:
    """Internal deterministic result for one evidence item."""

    allowed: bool
    reason_code: str


class ConfidentialityPolicy:
    """Pure policy rules for internal warnings and customer-safe selection."""

    _EXTERNAL_CLASSIFICATIONS = frozenset(
        {Classification.PUBLIC, Classification.CUSTOMER_SHAREABLE}
    )

    def evaluate_external(self, metadata: ShareabilityMetadata) -> ShareabilityDecision:
        """Allow only explicit, complete, customer-shareable metadata."""

        if metadata.classification is None:
            return ShareabilityDecision(False, "missing_classification")
        if metadata.external_shareable is not True:
            return ShareabilityDecision(False, "missing_or_false_shareability")
        if metadata.classification not in self._EXTERNAL_CLASSIFICATIONS:
            return ShareabilityDecision(False, "classification_not_shareable")
        return ShareabilityDecision(True, "shareable")

    def internal_warnings(
        self, metadata: ShareabilityMetadata
    ) -> tuple[PolicyWarning, ...]:
        """Return fixed warnings without exposing evidence identity or counts."""

        classification = metadata.classification
        if classification is Classification.RESTRICTED:
            return (
                PolicyWarning(
                    PolicyWarningCode.RESTRICTED_CONTENT_PRESENT,
                    PolicyWarningSeverity.ERROR,
                    "This internal answer may include restricted information; do not share it externally.",
                ),
            )
        if classification is Classification.CONFIDENTIAL:
            return (
                PolicyWarning(
                    PolicyWarningCode.CONFIDENTIAL_CONTENT_PRESENT,
                    PolicyWarningSeverity.WARNING,
                    "This internal answer may include confidential information; do not share it externally.",
                ),
            )
        if classification is Classification.INTERNAL:
            return (
                PolicyWarning(
                    PolicyWarningCode.INTERNAL_CONTENT_PRESENT,
                    PolicyWarningSeverity.WARNING,
                    "This internal answer may include information that is not customer-shareable.",
                ),
            )
        return ()
