"""Provider-agnostic text embedding: the `Embedder` contract plus the OpenAI adapter."""

from collections.abc import Sequence
from typing import Protocol

import openai

from ombuds.platform.ai.providers.base import ProviderUnavailableError

DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_MAX_RETRIES = 2
# The embeddings endpoint accepts up to 2048 inputs per request; stay well under it.
MAX_BATCH_SIZE = 256

# Same policy as `AnthropicProvider` (ADR-0006): only failures that mean "unavailable right now" are
# translated; a 4xx from bad input or a parsing bug propagates unchanged.
_RETRYABLE_OPENAI_ERRORS = (
    openai.APIConnectionError,  # also covers APITimeoutError
    openai.RateLimitError,
    openai.ConflictError,
    openai.InternalServerError,
)


class Embedder(Protocol):
    """Turns texts into fixed-length vectors, one per input, in input order."""

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Return one embedding per entry of `texts`."""
        ...


class OpenAIEmbedder:
    """Thin wrapper over the `openai` SDK's `embeddings.create`, batching large inputs.

    Retries and timeouts are delegated to the SDK client; once exhausted, a retryable failure is raised
    as `ProviderUnavailableError`.
    """

    def __init__(
        self,
        model: str,
        client: openai.OpenAI | None = None,
        *,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ) -> None:
        self._client = client or openai.OpenAI(timeout=timeout, max_retries=max_retries)
        self._model = model

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed `texts` in batches of `MAX_BATCH_SIZE`, preserving input order."""
        vectors: list[list[float]] = []
        for start in range(0, len(texts), MAX_BATCH_SIZE):
            batch = list(texts[start : start + MAX_BATCH_SIZE])
            try:
                response = self._client.embeddings.create(model=self._model, input=batch)
            except _RETRYABLE_OPENAI_ERRORS as exc:
                raise ProviderUnavailableError(str(exc)) from exc
            # The API tags each item with its input index; sort so order never depends on arrival order.
            vectors.extend(item.embedding for item in sorted(response.data, key=lambda item: item.index))
        return vectors
