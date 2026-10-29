"""Compare raw Anthropic, OpenAI, and DeepSeek outputs on the same prompt.

Throwaway exploration script for the foundations stage — not part of the app's runtime provider
layer (platform/ai/providers/). Prints text, latency, and an estimated cost
side by side so the SDKs can be eyeballed before any shared abstraction gets
built over them.

Run with: uv run python scripts/compare_providers.py
"""

import os
import time
from dataclasses import dataclass

import anthropic
import openai
from dotenv import load_dotenv

# Verify current pricing before trusting the cost estimate — rates change.
# https://platform.claude.com/docs/en/about-claude/pricing | https://platform.openai.com/docs/pricing
ANTHROPIC_MODEL = "claude-sonnet-5"
ANTHROPIC_PRICE_PER_MTOK = (2.00, 10.00)  # (input, output) USD per 1M tokens

OPENAI_MODEL = "gpt-4o"
OPENAI_PRICE_PER_MTOK = (2.50, 10.00)  # (input, output) USD per 1M tokens

# DeepSeek exposes an OpenAI-compatible endpoint — same SDK, different base_url.
# https://api-docs.deepseek.com/quick_start/pricing
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"
DEEPSEEK_PRICE_PER_MTOK = (0.27, 1.10)  # (input, output) USD per 1M tokens, cache miss

PROMPT = (
    "A passenger's flight from Berlin to Lisbon (1834 km) was cancelled "
    "9 days before departure due to a crew strike. The airline offered no "
    "rerouting. Is this passenger entitled to EU261 compensation? Answer in "
    "2-3 sentences."
)


@dataclass(frozen=True)
class ProviderResult:
    """One provider's response to the comparison prompt, with cost/latency."""

    provider: str
    model: str
    text: str
    latency_s: float
    input_tokens: int
    output_tokens: int
    cost_usd: float


def _estimate_cost(input_tokens: int, output_tokens: int, price_per_mtok: tuple[float, float]) -> float:
    input_price, output_price = price_per_mtok
    return (input_tokens * input_price + output_tokens * output_price) / 1_000_000


def call_anthropic(prompt: str) -> ProviderResult:
    """Send `prompt` to Anthropic and time/cost the call."""
    client = anthropic.Anthropic()  # picks up ANTHROPIC_API_KEY automatically

    start = time.perf_counter()
    response = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    latency_s = time.perf_counter() - start

    text = next((block.text for block in response.content if block.type == "text"), "")
    cost_usd = _estimate_cost(response.usage.input_tokens, response.usage.output_tokens, ANTHROPIC_PRICE_PER_MTOK)

    return ProviderResult(
        provider="anthropic",
        model=ANTHROPIC_MODEL,
        text=text,
        latency_s=latency_s,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        cost_usd=cost_usd,
    )


def _call_chat_completions(
    prompt: str,
    client: openai.OpenAI,
    *,
    provider: str,
    model: str,
    price_per_mtok: tuple[float, float],
) -> ProviderResult:
    """Send `prompt` through an OpenAI-compatible chat.completions client."""
    start = time.perf_counter()
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
    )
    latency_s = time.perf_counter() - start

    text = response.choices[0].message.content or ""
    usage = response.usage
    input_tokens = usage.prompt_tokens if usage else 0
    output_tokens = usage.completion_tokens if usage else 0
    cost_usd = _estimate_cost(input_tokens, output_tokens, price_per_mtok)

    return ProviderResult(
        provider=provider,
        model=model,
        text=text,
        latency_s=latency_s,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost_usd,
    )


def call_openai(prompt: str) -> ProviderResult:
    """Send `prompt` to OpenAI and time/cost the call."""
    client = openai.OpenAI()  # picks up OPENAI_API_KEY automatically
    return _call_chat_completions(
        prompt, client, provider="openai", model=OPENAI_MODEL, price_per_mtok=OPENAI_PRICE_PER_MTOK
    )


def call_deepseek(prompt: str) -> ProviderResult:
    """Send `prompt` to DeepSeek (OpenAI-compatible endpoint) and time/cost the call."""
    client = openai.OpenAI(api_key=os.environ["DEEPSEEK_API_KEY"], base_url=DEEPSEEK_BASE_URL)
    return _call_chat_completions(
        prompt, client, provider="deepseek", model=DEEPSEEK_MODEL, price_per_mtok=DEEPSEEK_PRICE_PER_MTOK
    )


def print_comparison(results: list[ProviderResult]) -> None:
    """Print each result's text, latency, tokens and cost, then a summary line."""
    for result in results:
        print(f"\n=== {result.provider} ({result.model}) ===")
        print(result.text)
        print(
            f"-- latency={result.latency_s:.2f}s "
            f"tokens_in={result.input_tokens} tokens_out={result.output_tokens} "
            f"est_cost=${result.cost_usd:.5f}"
        )

    print("\n=== summary ===")
    for result in results:
        print(f"{result.provider:10s} latency={result.latency_s:.2f}s  est_cost=${result.cost_usd:.5f}")


def main() -> None:
    load_dotenv()
    for key in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "DEEPSEEK_API_KEY"):
        if not os.environ.get(key):
            raise RuntimeError(f"{key} is not set — copy .env.example to .env and fill it in")

    results = [call_anthropic(PROMPT), call_openai(PROMPT), call_deepseek(PROMPT)]
    print_comparison(results)


if __name__ == "__main__":
    main()
