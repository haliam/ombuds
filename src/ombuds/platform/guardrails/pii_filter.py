"""PII filter: replaces structured personal identifiers in free text with typed placeholders.

Detection is regex plus a checksum where one exists (Luhn for cards, mod-97 for IBANs), so a random digit
string isn't mistaken for an account number. Redaction is one-way: there is no token vault, so the raw
value is gone once `redact` returns (ADR-0013).

Deliberately not handled: names and postal addresses, which regexes can't detect reliably, and booking
references or passport numbers that aren't introduced by a keyword — a bare 6-character code collides with
flight numbers like `LH1234`, and mangling flight facts would break eligibility. `RedactionResult` reports
counts per kind, never the matched values, so callers can log or audit that redaction happened safely.
"""

import re
from collections import Counter
from collections.abc import Callable
from enum import StrEnum
from re import Match

from pydantic import BaseModel, ConfigDict


class PiiKind(StrEnum):
    """Categories of identifier the filter recognises; the value is also the placeholder's label."""

    EMAIL = "EMAIL"
    IBAN = "IBAN"
    CARD = "CARD"
    PASSPORT = "PASSPORT"
    BOOKING_REF = "BOOKING_REF"
    PHONE = "PHONE"


class Finding(BaseModel):
    """How many values of one kind were redacted. Never carries the values themselves."""

    model_config = ConfigDict(frozen=True)

    kind: PiiKind
    count: int


class RedactionResult(BaseModel):
    """The redacted text plus a per-kind count of what was replaced."""

    model_config = ConfigDict(frozen=True)

    text: str
    findings: tuple[Finding, ...] = ()


IBAN_MIN_LENGTH = 15
IBAN_MAX_LENGTH = 34
CARD_MIN_DIGITS = 13
CARD_MAX_DIGITS = 19
PHONE_MIN_DIGITS = 8
PHONE_MAX_DIGITS = 15

_IBAN_MOD = 97
_IBAN_VALID_REMAINDER = 1

_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")
_IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){2,7}(?: ?[A-Z0-9]{1,3})?\b")
_CARD = re.compile(r"\b\d(?:[ -]?\d){12,18}\b")
# Group 1 is the keyword the value follows and is kept; the value needs a digit so that
# "passport control" is left alone.
_PASSPORT = re.compile(
    r"(\bpassport(?:\s+(?:no\.?|number|#))?\s*[:#]?\s*)((?=[A-Z0-9]*\d)[A-Z0-9]{6,9})\b", re.IGNORECASE
)
# The code is uppercase on purpose, and "NUMBER"/"CODE" are excluded so "BOOKING NUMBER" isn't a match.
_BOOKING_REF = re.compile(
    r"((?i:\b(?:booking|reservation|confirmation|pnr)(?:\s+(?:code|number|no\.?|ref(?:erence)?|id))?)\s*(?:is|:|#)?\s*)"
    r"(?!(?:NUMBER|CODE|PLEASE)\b)([A-Z0-9]{6})\b"
)
_PHONE = re.compile(
    r"(?<![\w+])(?:\+|00)\d{1,3}(?:[\s().-]*\d){6,12}\b"  # international, with a + or 00 prefix
    r"|(?<!\w)\(?\d{3}\)?[ .-]\d{3}[ .-]\d{4}(?!\w)"  # 555-123-4567, (555) 123-4567
    r"|(?<!\w)0\d{2,4}[ .-]\d{3,4}[ .-]\d{3,4}(?!\w)"  # 030 1234 5678
)


def _placeholder(kind: PiiKind) -> str:
    return f"[{kind}]"


def _luhn_valid(digits: str) -> bool:
    total = 0
    for position, char in enumerate(reversed(digits)):
        value = int(char)
        if position % 2 == 1:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return total % 10 == 0


def _iban_valid(candidate: str) -> bool:
    compact = candidate.replace(" ", "")
    if not IBAN_MIN_LENGTH <= len(compact) <= IBAN_MAX_LENGTH:
        return False
    rearranged = compact[4:] + compact[:4]
    number = "".join(str(int(char, 36)) for char in rearranged)
    return int(number) % _IBAN_MOD == _IBAN_VALID_REMAINDER


def _redact_email(match: Match[str]) -> str | None:
    return _placeholder(PiiKind.EMAIL)


def _redact_iban(match: Match[str]) -> str | None:
    candidate = match.group()
    if _iban_valid(candidate):
        return _placeholder(PiiKind.IBAN)
    # The pattern's optional trailing group can swallow the next word ("... 00 THE"); retry without it.
    head, separator, tail = candidate.rpartition(" ")
    if separator and _iban_valid(head):
        return f"{_placeholder(PiiKind.IBAN)} {tail}"
    return None


def _redact_card(match: Match[str]) -> str | None:
    digits = re.sub(r"[ -]", "", match.group())
    if CARD_MIN_DIGITS <= len(digits) <= CARD_MAX_DIGITS and _luhn_valid(digits):
        return _placeholder(PiiKind.CARD)
    return None


def _keep_prefix(kind: PiiKind) -> Callable[[Match[str]], str | None]:
    def replace(match: Match[str]) -> str | None:
        return f"{match.group(1)}{_placeholder(kind)}"

    return replace


def _redact_phone(match: Match[str]) -> str | None:
    digits = sum(char.isdigit() for char in match.group())
    if PHONE_MIN_DIGITS <= digits <= PHONE_MAX_DIGITS:
        return _placeholder(PiiKind.PHONE)
    return None


# Order matters: validated numeric identifiers go before the looser phone pattern, which would otherwise
# claim part of a card or IBAN, and email goes first so its digits can't be read as anything else.
_RULES: tuple[tuple[PiiKind, re.Pattern[str], Callable[[Match[str]], str | None]], ...] = (
    (PiiKind.EMAIL, _EMAIL, _redact_email),
    (PiiKind.IBAN, _IBAN, _redact_iban),
    (PiiKind.CARD, _CARD, _redact_card),
    (PiiKind.PASSPORT, _PASSPORT, _keep_prefix(PiiKind.PASSPORT)),
    (PiiKind.BOOKING_REF, _BOOKING_REF, _keep_prefix(PiiKind.BOOKING_REF)),
    (PiiKind.PHONE, _PHONE, _redact_phone),
)


def redact(text: str) -> RedactionResult:
    """Replace every recognised identifier in `text` with a `[KIND]` placeholder and count what was replaced.

    Idempotent: placeholders contain no digits or `@`, so redacting already-redacted text changes nothing.
    A candidate that fails its checksum is left untouched rather than redacted.
    """
    counts: Counter[PiiKind] = Counter()
    for kind, pattern, replacement in _RULES:

        def substitute(
            match: Match[str], kind: PiiKind = kind, replacement: Callable[[Match[str]], str | None] = replacement
        ) -> str:
            replaced = replacement(match)
            if replaced is None:
                return match.group()
            counts[kind] += 1
            return replaced

        text = pattern.sub(substitute, text)
    return RedactionResult(text=text, findings=tuple(Finding(kind=kind, count=count) for kind, count in counts.items()))


def redact_value(value: object) -> object:
    """Redact every string inside a JSON-like value (dicts, lists, tuples), leaving keys and other types alone.

    For tool-call arguments, whose shape isn't known to the guardrail layer.
    """
    if isinstance(value, str):
        return redact(value).text
    if isinstance(value, dict):
        return {key: redact_value(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [redact_value(item) for item in value]
    return value
