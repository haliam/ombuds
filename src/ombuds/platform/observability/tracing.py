"""OpenTelemetry tracing: one span per LLM turn, tool call and policy check (ADR-0017).

Spans carry identifiers, outcomes and counts, never claim text, prompts, tool arguments or results, so the
trace backend needs no PII handling of its own (ADR-0013). Instrumentation uses the global OTel API, which
is a no-op until `configure_tracing` installs a real provider, so library code never checks whether
tracing is on.
"""

import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import TypeVar

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter, SimpleSpanProcessor
from opentelemetry.trace import Span, Status, StatusCode

SERVICE_NAME = "ombuds"
_INSTRUMENTATION_NAME = "ombuds"

T = TypeVar("T")

EXPORTER_NONE = "none"
EXPORTER_CONSOLE = "console"
EXPORTER_OTLP = "otlp"


def configure_tracing(exporter: str) -> None:
    """Install the global tracer provider for `exporter` (`none`, `console` or `otlp`); a no-op for `none`.

    `console` writes to stderr, not stdout, because the MCP server speaks its protocol over stdout. `otlp`
    reads its endpoint from the standard `OTEL_EXPORTER_OTLP_*` environment variables. Call once per process,
    from a composition root.
    """
    if exporter == EXPORTER_NONE:
        return
    provider = TracerProvider(resource=Resource.create({"service.name": SERVICE_NAME}))
    if exporter == EXPORTER_CONSOLE:
        provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter(out=sys.stderr)))
    elif exporter == EXPORTER_OTLP:
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    else:
        raise ValueError(f"unknown OTEL_TRACES_EXPORTER: {exporter!r} (expected none, console or otlp)")
    trace.set_tracer_provider(provider)


@contextmanager
def start_span(name: str, **attributes: str | int | bool) -> Iterator[Span]:
    """Run the block inside a span named `name`; an exception escaping it marks the span as an error."""
    tracer = trace.get_tracer(_INSTRUMENTATION_NAME)
    with tracer.start_as_current_span(
        name, attributes=attributes, record_exception=False, set_status_on_exception=False
    ) as span:
        try:
            yield span
        except BaseException as exc:
            # Type only: exception messages can carry user-supplied text.
            span.set_status(Status(StatusCode.ERROR, type(exc).__name__))
            raise


def current_trace_id() -> str | None:
    """The active span's trace id as 32 hex characters, or None when no recording span is active."""
    context = trace.get_current_span().get_span_context()
    return trace.format_trace_id(context.trace_id) if context.is_valid else None


def trace_stream(
    name: str, events: Iterator[T], on_event: Callable[[Span, T], None] | None = None, **attributes: str | int | bool
) -> Iterator[T]:
    """Yield `events` unchanged inside a span named `name` that covers the whole stream.

    The span is made current only while the source produces each event, never across a `yield`: a consumer
    may resume the generator in another thread or context (FastAPI iterates sync generators in a threadpool),
    where detaching a context attached elsewhere fails. `on_event` can add attributes as events pass.
    """
    tracer = trace.get_tracer(_INSTRUMENTATION_NAME)
    span = tracer.start_span(name, attributes=attributes)
    try:
        while True:
            with trace.use_span(span, end_on_exit=False, record_exception=False, set_status_on_exception=False):
                try:
                    event = next(events)
                except StopIteration:
                    return
            if on_event is not None:
                on_event(span, event)
            yield event
    except GeneratorExit:
        raise
    except BaseException as exc:
        span.set_status(Status(StatusCode.ERROR, type(exc).__name__))
        raise
    finally:
        span.end()
