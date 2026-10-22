"""Shared unit-test fixtures."""

from collections.abc import Iterator

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from tests.api_auth import configure_api_auth

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


@pytest.fixture(autouse=True)
def api_auth_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every API test starts with the credentials configured; tests of the unset case remove them."""
    configure_api_auth(monkeypatch)
