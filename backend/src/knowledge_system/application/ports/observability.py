"""Framework-neutral ports for redacted telemetry and durable audit."""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import AbstractContextManager
from types import TracebackType
from typing import Literal, Protocol

from knowledge_system.domain.observability import QueryAuditRecord, SecurityAuditEvent

TelemetryValue = str | int | float | bool


class Span(Protocol):
    """Small span surface used by application code."""

    def set_attribute(self, key: str, value: TelemetryValue) -> None: ...

    def record_exception(self, error: BaseException) -> None: ...


class TelemetryPort(Protocol):
    """Operational telemetry; never an authorization or audit decision source."""

    def span(
        self,
        name: str,
        attributes: Mapping[str, TelemetryValue] | None = None,
    ) -> AbstractContextManager[Span]: ...

    def counter(
        self,
        name: str,
        value: int = 1,
        attributes: Mapping[str, TelemetryValue] | None = None,
    ) -> None: ...


class QueryAuditSink(Protocol):
    """Durable minimized query audit sink."""

    def record_query(self, record: QueryAuditRecord) -> None: ...


class SecurityAuditSink(Protocol):
    """Durable security/lifecycle audit sink."""

    def record_security_event(self, event: SecurityAuditEvent) -> None: ...


class AuditLogger(Protocol):
    """Content-free structured logger for operational correlation."""

    def query(self, record: QueryAuditRecord) -> None: ...

    def security_event(self, event: SecurityAuditEvent) -> None: ...


class NoopSpan:
    def set_attribute(self, key: str, value: TelemetryValue) -> None:
        del key, value

    def record_exception(self, error: BaseException) -> None:
        del error


class NoopTelemetry:
    """Safe default when the local collector is not configured."""

    def span(
        self,
        name: str,
        attributes: Mapping[str, TelemetryValue] | None = None,
    ) -> AbstractContextManager[Span]:
        from contextlib import nullcontext

        del name, attributes
        return nullcontext(NoopSpan())

    def counter(
        self,
        name: str,
        value: int = 1,
        attributes: Mapping[str, TelemetryValue] | None = None,
    ) -> None:
        del name, value, attributes


class _BestEffortSpan:
    def __init__(
        self,
        telemetry: TelemetryPort,
        name: str,
        attributes: Mapping[str, TelemetryValue] | None,
    ) -> None:
        self._telemetry = telemetry
        self._name = name
        self._attributes = attributes
        self._context: AbstractContextManager[Span] | None = None
        self._span: Span = NoopSpan()

    def __enter__(self) -> Span:
        try:
            self._context = self._telemetry.span(self._name, self._attributes)
            self._span = self._context.__enter__()
        except (OSError, RuntimeError, ValueError):
            self._context = None
            self._span = NoopSpan()
        return self._span

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        context = self._context
        if context is None:
            return False
        try:
            context.__exit__(exc_type, exc, traceback)
        except (OSError, RuntimeError, ValueError):
            return False
        return False


class BestEffortTelemetry:
    """Prevent telemetry transport failures from changing protected behavior."""

    def __init__(self, inner: TelemetryPort) -> None:
        self._inner = inner

    def span(
        self,
        name: str,
        attributes: Mapping[str, TelemetryValue] | None = None,
    ) -> AbstractContextManager[Span]:
        return _BestEffortSpan(self._inner, name, attributes)

    def counter(
        self,
        name: str,
        value: int = 1,
        attributes: Mapping[str, TelemetryValue] | None = None,
    ) -> None:
        try:
            self._inner.counter(name, value, attributes)
        except (OSError, RuntimeError, ValueError):
            return
