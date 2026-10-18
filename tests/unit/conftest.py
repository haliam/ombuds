"""Shared unit-test fixtures."""

from collections.abc import Iterator

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

_EXPORTER = InMemorySpanExporter()
_provider = TracerProvider()
_provider.add_span_processor(SimpleSpanProcessor(_EXPORTER))
# OTel allows the global provider to be set once per process, so it is installed at import and the exporter
# is cleared per test.
trace.set_tracer_provider(_provider)


@pytest.fixture
def spans() -> Iterator[InMemorySpanExporter]:
    """The in-memory exporter, empty at the start of each test; read finished spans with `get_finished_spans()`."""
    _EXPORTER.clear()
    yield _EXPORTER
    _EXPORTER.clear()
