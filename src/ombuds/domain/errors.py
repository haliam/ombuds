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


class PolicyDeniedError(ToolExecutionError):
    """Raised when the policy engine refuses a guarded action (ADR-0015); no approval request is created.

    A `ToolExecutionError` so it reaches the model or the MCP client as a tool error, with `reasons` as the
    machine-readable codes from the policy.
    """

    def __init__(self, action: str, reasons: tuple[str, ...]) -> None:
        super().__init__(f"policy denied {action}: {', '.join(reasons) or 'no reason given'}")
        self.action = action
        self.reasons = reasons
