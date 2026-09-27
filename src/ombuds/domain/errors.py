"""Domain-level error types."""


class ToolExecutionError(Exception):
    """Raised by a tool handler for an expected failure it can't complete a call for.

    Distinct from a `pydantic.ValidationError` (which `platform/ai/tool_loop.py`'s `ToolRegistry.dispatch`
    already catches on its own, before the handler even runs): this covers a failure discovered while
    *executing* an otherwise well-formed call — persistence unavailable, a downstream dependency down,
    anything a handler wants surfaced to the model as a tool error rather than crashing the whole turn.
    An exception that isn't `ToolExecutionError` (a bug, an unhandled case) is not caught by `dispatch`
    and propagates as-is, so it stays loud instead of being silently reported as "the tool failed".
    """
