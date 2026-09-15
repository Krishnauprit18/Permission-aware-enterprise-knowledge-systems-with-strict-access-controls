"""OpenTelemetry adapter for the local collector."""

from __future__ import annotations

import os
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass

from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.metrics import Counter as OTelCounter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import (
    PeriodicExportingMetricReader,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Span as OTelSpan

from knowledge_system.application.ports.observability import (
    NoopTelemetry,
    Span,
    TelemetryPort,
    TelemetryValue,
)


@dataclass(slots=True)
class _Span:
    span: OTelSpan

    def set_attribute(self, key: str, value: TelemetryValue) -> None:
        self.span.set_attribute(key, value)

    def record_exception(self, error: BaseException) -> None:
        self.span.record_exception(error)


class OpenTelemetryAdapter(TelemetryPort):
    """Export bounded spans and metrics to the local OTLP collector."""

    def __init__(
        self,
        endpoint: str = "http://127.0.0.1:4317",
        service_name: str = "permission-aware-knowledge-backend",
    ) -> None:
        resource = Resource.create({"service.name": service_name})
        tracer_provider = TracerProvider(resource=resource)
        tracer_provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True))
        )
        self._tracer = tracer_provider.get_tracer("knowledge_system")
        metric_reader = PeriodicExportingMetricReader(
            OTLPMetricExporter(endpoint=endpoint, insecure=True),
            export_interval_millis=15_000,
        )
        meter_provider = MeterProvider(
            resource=resource, metric_readers=[metric_reader]
        )
        self._meter = meter_provider.get_meter("knowledge_system")
        self._counters: dict[str, OTelCounter] = {}

    @contextmanager
    def span(
        self,
        name: str,
        attributes: Mapping[str, TelemetryValue] | None = None,
    ) -> Iterator[Span]:
        with self._tracer.start_as_current_span(name) as span:
            wrapped = _Span(span)
            for key, value in (attributes or {}).items():
                wrapped.set_attribute(key, value)
            try:
                yield wrapped
            except BaseException as error:
                wrapped.record_exception(error)
                raise

    def counter(
        self,
        name: str,
        value: int = 1,
        attributes: Mapping[str, TelemetryValue] | None = None,
    ) -> None:
        instrument = self._counters.get(name)
        if instrument is None:
            instrument = self._meter.create_counter(name)
            self._counters[name] = instrument
        instrument.add(
            value, {key: str(item) for key, item in (attributes or {}).items()}
        )


def create_local_telemetry() -> TelemetryPort:
    """Build the configured local exporter, with opt-out for tests/offline work."""

    if os.environ.get("KNOWLEDGE_OTEL_ENABLED", "0") != "1":
        return NoopTelemetry()
    endpoint = os.environ.get("KNOWLEDGE_OTEL_GRPC_ENDPOINT", "http://127.0.0.1:4317")
    service_name = os.environ.get(
        "KNOWLEDGE_OTEL_SERVICE_NAME", "permission-aware-knowledge-backend"
    )
    return OpenTelemetryAdapter(endpoint=endpoint, service_name=service_name)
