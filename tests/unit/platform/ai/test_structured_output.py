import pytest
from pydantic import BaseModel, ConfigDict

from ombuds.platform.ai.schemas.structured_output import StructuredOutputError, parse_structured_output


class _Verdict(BaseModel):
    model_config = ConfigDict(frozen=True)

    eligible: bool
    amount: float | None = None


def test_parse_structured_output_validates_a_clean_json_reply() -> None:
    result = parse_structured_output('{"eligible": true, "amount": 250}', _Verdict)

    assert result == _Verdict(eligible=True, amount=250)


def test_parse_structured_output_extracts_json_from_surrounding_prose() -> None:
    text = 'Sure, here is the decision:\n```json\n{"eligible": false}\n```\nLet me know if you need anything else.'

    result = parse_structured_output(text, _Verdict)

    assert result == _Verdict(eligible=False, amount=None)


def test_parse_structured_output_rejects_text_with_no_json_object() -> None:
    with pytest.raises(StructuredOutputError, match="no JSON object"):
        parse_structured_output("Please provide your flight details.", _Verdict)


def test_parse_structured_output_rejects_malformed_json() -> None:
    with pytest.raises(StructuredOutputError, match="not valid JSON"):
        parse_structured_output('{"eligible": true,}', _Verdict)


def test_parse_structured_output_rejects_json_that_fails_schema_validation() -> None:
    with pytest.raises(StructuredOutputError, match="does not match the required schema"):
        parse_structured_output('{"amount": 250}', _Verdict)
