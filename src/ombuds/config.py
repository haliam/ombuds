"""Config: environment-backed settings and the versioned-prompt loader (see AGENTS.md "Prompt versioning")."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROMPTS_DIR = Path(__file__).parent / "platform" / "prompts"

ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")
ANTHROPIC_FALLBACK_MODEL = os.environ.get("ANTHROPIC_FALLBACK_MODEL", "claude-haiku-4-5")
ANTHROPIC_TIMEOUT_SECONDS = float(os.environ.get("ANTHROPIC_TIMEOUT_SECONDS", "30"))
ANTHROPIC_MAX_RETRIES = int(os.environ.get("ANTHROPIC_MAX_RETRIES", "2"))

# Which prompt version is live per feature. Bump here (and in .env.example) after a new version
# passes evals/datasets/ — never edit an old version's file in place.
ACTIVE_PROMPT_VERSIONS = {"claims_triage": os.environ.get("CLAIMS_TRIAGE_PROMPT_VERSION", "v3")}


def load_prompt(feature: str) -> str:
    """Read the active versioned prompt for `feature` from `platform/prompts/<feature>/<version>.txt`."""
    version = ACTIVE_PROMPT_VERSIONS[feature]
    return (PROMPTS_DIR / feature / f"{version}.txt").read_text().strip()
