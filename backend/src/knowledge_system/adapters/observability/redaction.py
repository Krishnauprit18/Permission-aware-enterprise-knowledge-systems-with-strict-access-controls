"""Allowlist-based structured logging for security-sensitive paths."""

from __future__ import annotations

import logging
from collections.abc import Mapping

from knowledge_system.domain.observability import QueryAuditRecord, SecurityAuditEvent

_QUERY_FIELDS = frozenset(
    {
        "trace_id",
        "correlation_id",
        "pseudonymous_subject_id",
        "tenant_id",
        "query_hash",
        "query_length",
        "query_term_count",
        "authorization_fingerprint",
        "authorized_scope_size",
        "evidence_count",
        "document_version_count",
        "context_char_count",
        "input_token_count",
        "output_token_count",
        "outcome",
        "error_class",
        "latency_ms_by_stage",
    }
)
_SECURITY_FIELDS = frozenset(
    {
        "event_id",
        "event_type",
        "correlation_id",
        "trace_id",
        "pseudonymous_subject_id",
        "tenant_id",
        "outcome",
        "reason_code",
        "target_ref_hash",
    }
)
_SENSITIVE_KEY_PARTS = (
    "token",
    "cookie",
    "password",
    "secret",
    "authorization",
    "embedding",
    "vector",
    "prompt",
    "document_text",
    "chain_of_thought",
)


def _is_sensitive_key(key: str) -> bool:
    lowered = key.casefold()
    return any(part in lowered for part in _SENSITIVE_KEY_PARTS)


def redact_mapping(
    fields: Mapping[str, object], *, allowed: frozenset[str]
) -> dict[str, object]:
    """Keep only explicitly approved keys and never serialize sensitive values."""

    return {
        key: value
        for key, value in fields.items()
        if key in allowed and not _is_sensitive_key(key)
    }


def query_log_fields(record: QueryAuditRecord) -> dict[str, object]:
    """Project a query record to content-free operational log fields."""

    return redact_mapping(
        {
            "trace_id": record.trace_id,
            "correlation_id": record.correlation_id,
            "pseudonymous_subject_id": record.pseudonymous_subject_id,
            "tenant_id": record.tenant_id,
            "query_hash": record.query_hash,
            "query_length": record.query_length,
            "query_term_count": record.query_term_count,
            "authorization_fingerprint": record.authorization_fingerprint,
            "authorized_scope_size": record.authorized_scope_size,
            "evidence_count": len(record.evidence_ids),
            "document_version_count": len(record.document_version_ids),
            "context_char_count": record.context_char_count,
            "input_token_count": record.input_token_count,
            "output_token_count": record.output_token_count,
            "outcome": record.outcome.value,
            "error_class": record.error_class,
            "latency_ms_by_stage": dict(record.latency_ms_by_stage),
        },
        allowed=_QUERY_FIELDS,
    )


def security_log_fields(event: SecurityAuditEvent) -> dict[str, object]:
    """Project a security event without arbitrary payload attributes."""

    return redact_mapping(
        {
            "event_id": str(event.event_id),
            "event_type": event.event_type.value,
            "correlation_id": event.correlation_id,
            "trace_id": event.trace_id,
            "pseudonymous_subject_id": event.pseudonymous_subject_id,
            "tenant_id": event.tenant_id,
            "outcome": event.outcome.value,
            "reason_code": event.reason_code,
            "target_ref_hash": event.target_ref_hash,
        },
        allowed=_SECURITY_FIELDS,
    )


class RedactedAuditLogger:
    """Emit only allowlisted structured fields to the application logger."""

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self._logger = logger or logging.getLogger("knowledge_system.audit")

    def query(self, record: QueryAuditRecord) -> None:
        self._logger.info("query_audit", extra={"audit": query_log_fields(record)})

    def security_event(self, event: SecurityAuditEvent) -> None:
        self._logger.info("security_audit", extra={"audit": security_log_fields(event)})
