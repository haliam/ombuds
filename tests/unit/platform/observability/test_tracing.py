from collections.abc import Iterator

import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

from ombuds.platform.observability.tracing import configure_tracing, current_trace_id, start_span, trace_stream


def test_no_trace_id_outside_a_span() -> None:
    assert current_trace_id() is None


def test_trace_id_inside_a_span_matches_the_exported_span(spans: InMemorySpanExporter) -> None:
    with start_span("work", claim_id="c-1"):
        trace_id = current_trace_id()

    (span,) = spans.get_finished_spans()
    assert trace_id is not None and len(trace_id) == 32
    assert span.context is not None and f"{span.context.trace_id:032x}" == trace_id
    assert dict(span.attributes or {}) == {"claim_id": "c-1"}


def test_exception_marks_span_as_error_with_type_only(spans: InMemorySpanExporter) -> None:
    with pytest.raises(ValueError), start_span("work"):
        raise ValueError("jane@example.com")

    (span,) = spans.get_finished_spans()
    assert span.status.status_code is StatusCode.ERROR
    assert span.status.description == "ValueError"
    assert not span.events


def test_trace_stream_passes_events_through_and_ends_span_once(spans: InMemorySpanExporter) -> None:
    seen: list[int] = []

    out = list(trace_stream("stream", iter([1, 2, 3]), lambda span, event: seen.append(event), kind="x"))

    assert out == [1, 2, 3] == seen
    (span,) = spans.get_finished_spans()
    assert span.name == "stream"
    assert dict(span.attributes or {}) == {"kind": "x"}


def test_trace_stream_makes_span_current_only_while_producing(spans: InMemorySpanExporter) -> None:
    def source() -> Iterator[str | int | None]:
        yield current_trace_id()

    stream = trace_stream("stream", source())

    assert next(stream) is not None
    assert current_trace_id() is None
    list(stream)


def test_trace_stream_marks_error_when_source_raises(spans: InMemorySpanExporter) -> None:
    def source() -> Iterator[str | int | None]:
        yield 1
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        list(trace_stream("stream", source()))

    (span,) = spans.get_finished_spans()
    assert span.status.status_code is StatusCode.ERROR


def test_configure_tracing_rejects_unknown_exporter() -> None:
    with pytest.raises(ValueError, match="unknown OTEL_TRACES_EXPORTER"):
        configure_tracing("zipkin")


def test_configure_tracing_none_is_a_noop() -> None:
    configure_tracing("none")
