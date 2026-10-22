"""Config: environment-backed settings and the versioned-prompt loader (see AGENTS.md "Prompt versioning")."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROMPTS_DIR = Path(__file__).parent / "platform" / "prompts"

ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")
ANTHROPIC_FALLBACK_MODEL = os.environ.get("ANTHROPIC_FALLBACK_MODEL", "claude-haiku-4-5")
ANTHROPIC_TIMEOUT_SECONDS = float(os.environ.get("ANTHROPIC_TIMEOUT_SECONDS", "30"))
ANTHROPIC_MAX_RETRIES = int(os.environ.get("ANTHROPIC_MAX_RETRIES", "2"))

ANTHROPIC_MAX_TOKENS = int(os.environ.get("ANTHROPIC_MAX_TOKENS", "1024"))

# LLM spend limits (ADR-0018). Per-process caps on estimated USD and on tokens; a turn is refused once either is
# reached. The USD figure comes from the price table below, so keep that table current; models missing from it are
# charged at the conservative LLM_UNKNOWN_PRICE. Set the provider-side spend limit too: this ledger is an estimate.
LLM_BUDGET_MAX_USD = float(os.environ.get("LLM_BUDGET_MAX_USD", "1.00"))
LLM_BUDGET_MAX_TOKENS = int(os.environ.get("LLM_BUDGET_MAX_TOKENS", "500000"))
# (input, output) USD per million tokens. Verify against the provider's pricing page when changing models.
LLM_PRICES_USD_PER_MTOK = {"claude-sonnet-5": (3.0, 15.0), "claude-haiku-4-5": (1.0, 5.0)}
LLM_UNKNOWN_PRICE_USD_PER_MTOK = (15.0, 75.0)

# Embeddings for RAG. text-embedding-3-small emits 1536 dims, matching `kb_chunks.embedding vector(1536)`.
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small")

# Postgres (relational + pgvector, ADR-0010). There is no credential default: `database_url()` raises unless
# DATABASE_URL is set, or OMBUDS_ALLOW_DEV_DEFAULTS=1 opts in to the throwaway local one below.
_DEV_DATABASE_URL = "postgresql://ombuds:ombuds@localhost:5433/ombuds"
DATABASE_POOL_MAX_SIZE = int(os.environ.get("DATABASE_POOL_MAX_SIZE", "10"))

# OPA policy server (ADR-0015) and the payout ceiling it enforces. Payments above the limit are denied at submit.
# The default limit blocks EU261's EUR 600 tier and allows 250/400; the right value is a business call.
OPA_URL = os.environ.get("OPA_URL", "http://localhost:8181")
OPA_TIMEOUT_SECONDS = float(os.environ.get("OPA_TIMEOUT_SECONDS", "2"))
PAYOUT_LIMIT_EUR = int(os.environ.get("PAYOUT_LIMIT_EUR", "400"))

# OpenTelemetry (ADR-0017): `none` (default, spans are no-ops), `console` (stderr) or `otlp`. The OTLP endpoint comes
# from the standard OTEL_EXPORTER_OTLP_ENDPOINT / OTEL_EXPORTER_OTLP_HEADERS variables.
OTEL_TRACES_EXPORTER = os.environ.get("OTEL_TRACES_EXPORTER", "none")

# API authentication (ADR-0019): a bearer token for triage, another for approve/deny, and the name recorded as the
# approver. No defaults: `api_auth()` is read per request, and any unset value makes the API refuse requests.

# Which prompt version is live per feature. Bump here (and in .env.example) after a new version
# passes evals/datasets/ — never edit an old version's file in place.
ACTIVE_PROMPT_VERSIONS = {"claims_triage": os.environ.get("CLAIMS_TRIAGE_PROMPT_VERSION", "v4")}


def database_url() -> str:
    """The Postgres connection string. Read at the point of use, so importing `config` never needs a database."""
    if url := os.environ.get("DATABASE_URL"):
        return url
    if os.environ.get("OMBUDS_ALLOW_DEV_DEFAULTS") == "1":
        return _DEV_DATABASE_URL
    raise RuntimeError(
        "DATABASE_URL is not set. Copy .env.example to .env and set POSTGRES_PASSWORD and DATABASE_URL "
        "(or set OMBUDS_ALLOW_DEV_DEFAULTS=1 for a throwaway local database)."
    )


@dataclass(frozen=True)
class ApiAuth:
    """The API's credentials. An empty string means unset, which the API treats as "refuse everything"."""

    triage_token: str
    approver_token: str
    approver: str


def api_auth() -> ApiAuth:
    """The API credentials from the environment. Read at the point of use, so tests and restarts see current values."""
    return ApiAuth(
        triage_token=os.environ.get("OMBUDS_TRIAGE_TOKEN", ""),
        approver_token=os.environ.get("OMBUDS_APPROVER_TOKEN", ""),
        approver=os.environ.get("OMBUDS_APPROVER", ""),
    )


def load_prompt(feature: str) -> str:
    """Read the active versioned prompt for `feature` from `platform/prompts/<feature>/<version>.txt`."""
    version = ACTIVE_PROMPT_VERSIONS[feature]
    return (PROMPTS_DIR / feature / f"{version}.txt").read_text().strip()
