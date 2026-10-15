"""Logging: a handler-level filter that keeps PII out of every log line.

Nothing in the codebase should log a claim's text, but exception messages and third-party loggers can still
carry user-supplied strings, so the filter redacts the message template, its string arguments, the traceback text and
any stack info with `pii_filter.redact` — the same one-way redaction used on requests (ADR-0013). It is attached to
handlers, not loggers, because a logger's filters don't apply to records propagated from its children.
"""

import logging
import sys
from logging import Handler, LogRecord

from ombuds.platform.guardrails.pii_filter import redact

# uvicorn installs its own non-propagating handlers, so they have to be covered explicitly.
_THIRD_PARTY_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")


class PiiRedactingFilter(logging.Filter):
    """Rewrites a record so its message, traceback and stack info contain no recognised PII."""

    def filter(self, record: LogRecord) -> bool:
        # Redact the template and each string arg separately instead of flattening to one string: uvicorn's
        # access formatter unpacks `record.args` as a tuple, so it has to keep its shape.
        record.msg = redact(str(record.msg)).text
        if isinstance(record.args, tuple):
            record.args = tuple(redact(a).text if isinstance(a, str) else a for a in record.args)
        elif isinstance(record.args, dict):
            record.args = {k: redact(v).text if isinstance(v, str) else v for k, v in record.args.items()}
        if record.exc_info and not record.exc_text:
            record.exc_text = logging.Formatter().formatException(record.exc_info)
        if record.exc_text:
            record.exc_text = redact(record.exc_text).text
        if record.stack_info:
            record.stack_info = redact(record.stack_info).text
        return True


def configure_logging() -> None:
    """Attach `PiiRedactingFilter` to every root and uvicorn handler; safe to call more than once.

    With no handler configured, Python would fall back to an unfiltered `lastResort` handler, so a stderr
    one is added first. It's stderr, not stdout, because the MCP server speaks its protocol over stdout.
    """
    root = logging.getLogger()
    if not root.handlers:
        root.addHandler(logging.StreamHandler(sys.stderr))
    handlers: list[Handler] = list(root.handlers)
    for name in _THIRD_PARTY_LOGGERS:
        handlers.extend(logging.getLogger(name).handlers)
    for handler in handlers:
        if not any(isinstance(existing, PiiRedactingFilter) for existing in handler.filters):
            handler.addFilter(PiiRedactingFilter())
