"""Token usage as a provider-agnostic value, so cost control never depends on one SDK's response type."""

from pydantic import BaseModel, ConfigDict


class TokenUsage(BaseModel):
    """Tokens one model turn consumed, as the provider reported them."""

    model_config = ConfigDict(frozen=True)

    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens
