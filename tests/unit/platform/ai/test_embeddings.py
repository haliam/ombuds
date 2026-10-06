from types import SimpleNamespace

import httpx2
import openai
import pytest

from ombuds.platform.ai.embeddings import MAX_BATCH_SIZE, OpenAIEmbedder
from ombuds.platform.ai.providers.base import ProviderUnavailableError


def _request() -> httpx2.Request:
    return httpx2.Request("POST", "https://api.openai.com/v1/embeddings")


class _FakeEmbeddings:
    """Stands in for `openai.OpenAI().embeddings`: returns [len(text)] per input, or raises a fixed error."""

    def __init__(self, error: Exception | None = None, *, shuffle: bool = False) -> None:
        self._error = error
        self._shuffle = shuffle
        self.calls: list[list[str]] = []

    def create(self, *, model: str, input: list[str]) -> SimpleNamespace:
        if self._error:
            raise self._error
        self.calls.append(input)
        items = [SimpleNamespace(index=i, embedding=[float(len(text))]) for i, text in enumerate(input)]
        return SimpleNamespace(data=list(reversed(items)) if self._shuffle else items)


def _embedder(embeddings: _FakeEmbeddings) -> OpenAIEmbedder:
    client = SimpleNamespace(embeddings=embeddings)
    return OpenAIEmbedder("text-embedding-3-small", client=client)  # type: ignore[arg-type]


def test_embed_returns_one_vector_per_text_in_input_order_even_if_the_api_reorders() -> None:
    embedder = _embedder(_FakeEmbeddings(shuffle=True))

    assert embedder.embed(["a", "bbb", "cc"]) == [[1.0], [3.0], [2.0]]


def test_embed_splits_large_inputs_into_batches() -> None:
    embeddings = _FakeEmbeddings()
    texts = ["x"] * (MAX_BATCH_SIZE + 1)

    vectors = _embedder(embeddings).embed(texts)

    assert len(vectors) == len(texts)
    assert [len(call) for call in embeddings.calls] == [MAX_BATCH_SIZE, 1]


def test_embed_of_no_texts_makes_no_request() -> None:
    embeddings = _FakeEmbeddings()

    assert _embedder(embeddings).embed([]) == []
    assert embeddings.calls == []


def test_embed_wraps_a_retryable_sdk_error_as_provider_unavailable() -> None:
    embedder = _embedder(_FakeEmbeddings(openai.APIConnectionError(request=_request())))

    with pytest.raises(ProviderUnavailableError):
        embedder.embed(["a"])


def test_embed_propagates_a_non_retryable_sdk_error_unchanged() -> None:
    response = httpx2.Response(400, request=_request(), json={"error": {"message": "bad"}})
    error = openai.BadRequestError("bad", response=response, body=None)

    with pytest.raises(openai.BadRequestError):
        _embedder(_FakeEmbeddings(error)).embed(["a"])
