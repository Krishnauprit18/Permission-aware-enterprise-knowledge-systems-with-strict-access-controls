"""Allowlisted authentication logging fields."""

from collections.abc import Mapping

_SAFE_FIELDS = frozenset(
    {"event", "outcome", "reason_code", "correlation_id", "duration_ms"}
)


def safe_auth_log_fields(fields: Mapping[str, object]) -> dict[str, object]:
    """Return only non-sensitive, explicitly approved auth event fields."""

    return {key: value for key, value in fields.items() if key in _SAFE_FIELDS}
