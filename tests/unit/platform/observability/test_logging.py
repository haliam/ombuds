import io
import logging
from collections.abc import Iterator

import pytest

from ombuds.platform.observability.logging import PiiRedactingFilter, configure_logging


@pytest.fixture
def captured() -> Iterator[tuple[logging.Logger, io.StringIO]]:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.addFilter(PiiRedactingFilter())
    logger = logging.getLogger("test_pii_logging")
    logger.propagate = False
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    yield logger, stream
    logger.removeHandler(handler)


def test_the_message_is_redacted_after_its_args_are_applied(captured) -> None:
    logger, stream = captured

    logger.warning("claim from %s failed", "jane.doe@example.com")

    assert stream.getvalue() == "claim from [EMAIL] failed\n"


def test_a_traceback_is_redacted(captured) -> None:
    logger, stream = captured

    try:
        raise ValueError("bad input from jane.doe@example.com")
    except ValueError:
        logger.exception("lookup failed")

    output = stream.getvalue()
    assert "jane.doe@example.com" not in output
    assert "ValueError: bad input from [EMAIL]" in output


def test_clean_messages_are_unchanged(captured) -> None:
    logger, stream = captured

    logger.info("triaged claim %s in %d turns", "CLM-1", 3)

    assert stream.getvalue() == "triaged claim CLM-1 in 3 turns\n"


def test_configure_logging_filters_every_root_handler_once() -> None:
    root = logging.getLogger()
    handler = logging.StreamHandler(io.StringIO())
    root.addHandler(handler)
    try:
        configure_logging()
        configure_logging()

        assert [type(f) for f in handler.filters] == [PiiRedactingFilter]
    finally:
        root.removeHandler(handler)


def test_args_keep_their_tuple_shape_for_uvicorn_style_formatters(captured) -> None:
    logger, _ = captured
    seen: list[object] = []

    def spy(record: logging.LogRecord) -> bool:
        seen.append(record.args)
        return True

    # Handler filters run in order, so this one sees the record after the PII filter has rewritten it.
    logger.handlers[0].addFilter(spy)

    logger.info('%s - "%s %s HTTP/%s" %d', "10.0.0.1", "GET", "/u/jane.doe@example.com", "1.1", 200)

    assert seen == [("10.0.0.1", "GET", "/u/[EMAIL]", "1.1", 200)]
