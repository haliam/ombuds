"""Spend limits for LLM calls (ADR-0018): a shared ledger of tokens and estimated USD, with a hard stop.

`UsageBudget` is the ledger; `providers/budgeted.py` charges it after each turn and refuses a turn once a cap is
reached. The USD figure is an estimate from a price table, not the provider's invoice, so the provider-side spend
limit stays the real backstop. The ledger is per process: it resets on restart and each worker has its own.
"""

import threading
from dataclasses import dataclass

from ombuds.platform.ai.usage import TokenUsage

_TOKENS_PER_MTOK = 1_000_000


class BudgetExceededError(Exception):
    """Raised before an LLM turn when the budget is already spent; no call is made."""


@dataclass(frozen=True)
class ModelPrice:
    """USD per million tokens."""

    input_per_mtok: float
    output_per_mtok: float

    def cost(self, usage: TokenUsage) -> float:
        micro = usage.input_tokens * self.input_per_mtok + usage.output_tokens * self.output_per_mtok
        return micro / _TOKENS_PER_MTOK


class UsageBudget:
    """Thread-safe running total of tokens and estimated USD, checked before every turn.

    A model missing from `prices` is charged at `unknown_price`, which should be set high: overcounting
    stops early, undercounting overspends. In-flight turns are not reserved, so concurrent requests can
    overshoot a cap by the turns already running.
    """

    def __init__(
        self, *, max_usd: float, max_tokens: int, prices: dict[str, ModelPrice], unknown_price: ModelPrice
    ) -> None:
        self._max_usd = max_usd
        self._max_tokens = max_tokens
        self._prices = prices
        self._unknown_price = unknown_price
        self._lock = threading.Lock()
        self._usd = 0.0
        self._tokens = 0

    @property
    def spent_usd(self) -> float:
        return self._usd

    @property
    def spent_tokens(self) -> int:
        return self._tokens

    def check(self) -> None:
        """Raise `BudgetExceededError` if either cap is already reached."""
        with self._lock:
            if self._usd >= self._max_usd:
                raise BudgetExceededError(f"LLM spend cap reached: ~${self._usd:.4f} of ${self._max_usd:.2f}")
            if self._tokens >= self._max_tokens:
                raise BudgetExceededError(f"LLM token cap reached: {self._tokens} of {self._max_tokens}")

    def charge(self, model: str, usage: TokenUsage) -> None:
        """Add one turn's usage to the ledger."""
        cost = self._prices.get(model, self._unknown_price).cost(usage)
        with self._lock:
            self._usd += cost
            self._tokens += usage.total
