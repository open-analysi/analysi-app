"""OpenTelemetry configuration for distributed tracing.

No-op by default: tracing only activates when OTEL_EXPORTER_OTLP_ENDPOINT is set.
This makes the code OTEL-ready without requiring a collector in development.

When we move to k8s, set the env var and traces flow automatically.
"""

import os

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider

_configured = False


def configure_telemetry(
    *,
    service_name: str | None = None,
) -> None:
    """Configure OpenTelemetry tracing.

    Args:
        service_name: Override the service name. Falls back to
            OTEL_SERVICE_NAME env var, then "analysi-api".
    """
    global _configured
    if _configured:
        return
    _configured = True

    resolved_name = service_name or os.getenv("OTEL_SERVICE_NAME") or "analysi-api"
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    environment = os.getenv("ENVIRONMENT") or "development"

    resource = Resource.create(
        {
            "service.name": resolved_name,
            "deployment.environment": environment,
        }
    )

    provider = TracerProvider(resource=resource)

    if endpoint:
        # Only configure exporter when endpoint is set
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        exporter = OTLPSpanExporter(endpoint=endpoint)
        provider.add_span_processor(BatchSpanProcessor(exporter))

    trace.set_tracer_provider(provider)


def get_tracer(name: str = __name__) -> trace.Tracer:
    """Get an OpenTelemetry tracer."""
    return trace.get_tracer(name)


def inject_trace_context(logger: object, method_name: str, event_dict: dict) -> dict:
    """Structlog processor that adds trace_id and span_id from active OTEL span."""
    span = trace.get_current_span()
    ctx = span.get_span_context()

    if ctx and ctx.trace_id:
        event_dict.setdefault("trace_id", format(ctx.trace_id, "032x"))
        event_dict.setdefault("span_id", format(ctx.span_id, "016x"))

    return event_dict
