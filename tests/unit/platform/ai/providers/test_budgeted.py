from collections.abc import Iterator, Sequence

import pytest

from ombuds.platform.ai.budget import BudgetExceededError, ModelPrice, UsageBudget
from ombuds.platform.ai.providers.base import ProviderTurn
from ombuds.platform.ai.providers.budgeted import BudgetedProvider
from ombuds.platform.ai.schemas.tool_calls import ToolDefinition
from ombuds.platform.ai.streaming import StreamEvent, TurnDone
from ombuds.platform.ai.usage import TokenUsage

USAGE = TokenUsage(input_tokens=60, output_tokens=40)


class _Inner:
    def __init__(self) -> None:
        self.calls = 0

    def run_turn(
        self, messages: list[dict[str, object]], tools: Sequence[ToolDefinition], *, system: str
    ) -> ProviderTurn:
        self.calls += 1
        return ProviderTurn(text="", tool_calls=(), stop_reason="end_turn", content=[], usage=USAGE)

    def stream_turn(
        self, messages: list[dict[str, object]], tools: Sequence[ToolDefinition], *, system: str
    ) -> Iterator[StreamEvent]:
        self.calls += 1
        yield TurnDone(text="", tool_calls=(), stop_reason="end_turn", content=[], usage=USAGE)


def _budget(max_tokens: int) -> UsageBudget:
    price = ModelPrice(input_per_mtok=1.0, output_per_mtok=1.0)
    return UsageBudget(max_usd=100.0, max_tokens=max_tokens, prices={}, unknown_price=price)


def test_run_turn_charges_the_reported_usage() -> None:
    budget = _budget(1000)

    BudgetedProvider(_Inner(), "m", budget).run_turn([], [], system="s")

    assert budget.spent_tokens == 100


def test_run_turn_refuses_without_calling_the_model_once_the_budget_is_spent() -> None:
    inner = _Inner()
    provider = BudgetedProvider(inner, "m", _budget(100))
    provider.run_turn([], [], system="s")

    with pytest.raises(BudgetExceededError):
        provider.run_turn([], [], system="s")

    assert inner.calls == 1


def test_stream_turn_charges_on_turn_done_and_then_refuses() -> None:
    budget = _budget(100)
    inner = _Inner()
    provider = BudgetedProvider(inner, "m", budget)

    events = list(provider.stream_turn([], [], system="s"))

    assert isinstance(events[-1], TurnDone)
    assert budget.spent_tokens == 100
    with pytest.raises(BudgetExceededError):
        list(provider.stream_turn([], [], system="s"))
    assert inner.calls == 1
