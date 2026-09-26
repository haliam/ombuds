"""Structured output validation: parse a model's final reply as JSON and validate it against a schema.

The resulting `StructuredOutputError` message is written to be fed straight back to the model as a repair
prompt (see `triage_use_case.py`), not just logged — so its wording should stay concrete and actionable.
"""

import json
from typing import TypeVar

from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)


class StructuredOutputError(Exception):
    """A model's reply wasn't valid JSON, or didn't validate against the expected schema."""


def parse_structured_output(text: str, schema: type[T]) -> T:
    """Parse `text` as JSON and validate it against `schema`, raising `StructuredOutputError` on failure.

    Extracts the outermost `{...}` span before parsing, since models don't reliably emit *only* JSON even
    when asked to (e.g. they wrap it in a ```json fence or add a leading sentence).
    """
    payload = _extract_json_object(text)

    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise StructuredOutputError(f"reply is not valid JSON: {exc}") from exc

    try:
        return schema.model_validate(data)
    except ValidationError as exc:
        raise StructuredOutputError(f"reply does not match the required schema: {exc}") from exc


def _extract_json_object(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise StructuredOutputError("reply contains no JSON object")
    return text[start : end + 1]
