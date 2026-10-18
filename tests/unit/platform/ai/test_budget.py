import pytest

from ombuds.platform.ai.budget import BudgetExceededError, ModelPrice, UsageBudget
from ombuds.platform.ai.usage import TokenUsage

PRICE = ModelPrice(input_per_mtok=3.0, output_per_mtok=15.0)


def _budget(max_usd: float = 1.0, max_tokens: int = 1_000_000) -> UsageBudget:
    return UsageBudget(
        max_usd=max_usd,
        max_tokens=max_tokens,
        prices={"known": PRICE},
        unknown_price=ModelPrice(input_per_mtok=30.0, output_per_mtok=150.0),
    )


def test_charge_adds_tokens_and_priced_usd() -> None:
    budget = _budget()

    budget.charge("known", TokenUsage(input_tokens=1_000_000, output_tokens=100_000))

    assert budget.spent_tokens == 1_100_000
    assert budget.spent_usd == pytest.approx(3.0 + 1.5)


def test_unknown_model_is_charged_at_the_conservative_price() -> None:
    budget = _budget()

    budget.charge("mystery", TokenUsage(input_tokens=1_000_000))

    assert budget.spent_usd == pytest.approx(30.0)


def test_check_passes_under_the_caps_and_raises_once_usd_is_reached() -> None:
    budget = _budget(max_usd=0.01)
    budget.check()

    budget.charge("known", TokenUsage(input_tokens=10_000))  # 0.03 USD

    with pytest.raises(BudgetExceededError, match="spend cap"):
        budget.check()


def test_check_raises_once_the_token_cap_is_reached() -> None:
    budget = _budget(max_tokens=100)

    budget.charge("known", TokenUsage(input_tokens=60, output_tokens=40))

    with pytest.raises(BudgetExceededError, match="token cap"):
        budget.check()
