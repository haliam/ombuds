"""Injection detection: flags passenger text that tries to give the model instructions instead of facts.

A claim is data. Text that tells the model to ignore its rules, take on a new role, reveal its prompt, call a
named tool, or smuggles chat-template delimiters is not a description of a delayed flight, so a hit is a reason
to hand the claim to a human rather than to the model (ADR-0014).

Detection is heuristic: case-insensitive regexes over text first normalised (NFKC, zero-width and control
characters dropped, whitespace collapsed, letter-by-letter spacing joined) so that trivial obfuscation doesn't
slip past, plus a decode-and-rescan of base64-looking blobs. It will miss a determined, novel attacker; it is
one layer, and the approval gate and tool scoping (ADR-0009) hold regardless. Like `RedactionResult`, a result
reports counts per kind and never the matched text, so callers can log or audit a hit safely.
"""

import base64
import binascii
import re
import unicodedata
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class InjectionKind(StrEnum):
    """Categories of injection attempt the detector recognises."""

    INSTRUCTION_OVERRIDE = "INSTRUCTION_OVERRIDE"
    ROLE_HIJACK = "ROLE_HIJACK"
    PROMPT_EXFIL = "PROMPT_EXFIL"
    TOOL_COMMAND = "TOOL_COMMAND"
    DELIMITER_SPOOF = "DELIMITER_SPOOF"
    ENCODED_PAYLOAD = "ENCODED_PAYLOAD"


class Finding(BaseModel):
    """How many matches of one kind were found. Never carries the matched text."""

    model_config = ConfigDict(frozen=True)

    kind: InjectionKind
    count: int


class InjectionResult(BaseModel):
    """What the detector found in a piece of text; empty `findings` means nothing suspicious."""

    model_config = ConfigDict(frozen=True)

    findings: tuple[Finding, ...] = ()

    @property
    def suspicious(self) -> bool:
        return bool(self.findings)


_FLAGS = re.IGNORECASE | re.MULTILINE

_OVERRIDE_VERB = r"(?:ignore|disregard|forget|override|bypass)"
_PATTERNS: dict[InjectionKind, tuple[re.Pattern[str], ...]] = {
    InjectionKind.INSTRUCTION_OVERRIDE: tuple(
        re.compile(p, _FLAGS)
        for p in (
            # "ignore all previous instructions", "disregard the above rules" — needs the noun, so
            # "ignore the earlier rebooking email" is left alone.
            rf"\b{_OVERRIDE_VERB}\b(?:\W+\w+){{0,3}}?\W+(?:previous|prior|above|earlier|preceding|system|your|all)\b"
            r"(?:\W+\w+){0,2}?\W+(?:instructions?|prompts?|rules|guidelines|directives)\b",
            r"\b(?:new|updated|real|actual) (?:instructions?|system prompt)\s*:",
            r"\bfrom now on,? (?:you|ignore|always|only)\b",
            r"\bignoriere (?:alle )?(?:vorherigen|bisherigen|obigen) anweisungen\b",
            r"\bignore[zr]? (?:toutes )?(?:les )?instructions pr[ée]c[ée]dentes\b",
            r"\bignora (?:todas )?las instrucciones anteriores\b",
        )
    ),
    InjectionKind.ROLE_HIJACK: tuple(
        re.compile(p, _FLAGS)
        for p in (
            r"\byou are (?:now|no longer)\b",
            r"\bact as (?:an? )?(?:admin|administrator|developer|system|root|supervisor)\b",
            r"\bpretend (?:to be|you are|that you)\b",
            r"\b(?:developer|jailbreak|dan|god|sudo|admin) mode\b",
        )
    ),
    InjectionKind.PROMPT_EXFIL: tuple(
        re.compile(p, _FLAGS)
        for p in (
            r"\b(?:reveal|show|print|repeat|output|display|leak|tell me)\b(?:\W+\w+){0,4}?\W+"
            r"(?:system prompt|your (?:initial |original |hidden )?(?:instructions|prompt|rules)"
            r"|(?:the )?(?:initial|original|hidden) (?:instructions|prompt|rules))\b",
            r"\bwhat (?:is|are|were) your (?:system prompt|instructions|rules)\b",
        )
    ),
    InjectionKind.TOOL_COMMAND: tuple(
        re.compile(p, _FLAGS)
        for p in (
            r"\b(?:issue_payment|log_claim|check_eligibility|search_kb)\b",
            r"\b(?:auto[- ]?approve|skip (?:the )?(?:approval|human review|verification|approval gate))\b",
        )
    ),
    InjectionKind.DELIMITER_SPOOF: tuple(
        re.compile(p, _FLAGS)
        for p in (
            r"<\s*/?\s*(?:system|assistant|developer|tool|instructions?)\s*>",
            r"\[/?(?:INST|SYS|SYSTEM)\]",
            r"<\|[a-z_]+\|>",
            r"^\s*(?:#{2,}\s*)?(?:system|assistant|developer)\s*:",
            r"```\s*system\b",
        )
    ),
}

_ZERO_WIDTH = dict.fromkeys([0x200B, 0x200C, 0x200D, 0x200E, 0x200F, 0x2060, 0xFEFF, 0x00AD])
_SPACED_LETTERS = re.compile(r"(?<!\w)(?:\w ){3,}\w(?!\w)")
_BASE64_BLOB = re.compile(r"[A-Za-z0-9+/]{24,}={0,2}")


def _normalise(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).translate(_ZERO_WIDTH)
    return "".join(" " if unicodedata.category(c) == "Cc" and c not in "\n\t" else c for c in text)


def _collapse_whitespace(text: str) -> str:
    return re.sub(r"[ \t]+", " ", text)


def _count_by_kind(text: str) -> dict[InjectionKind, int]:
    counts: dict[InjectionKind, int] = {}
    for kind, patterns in _PATTERNS.items():
        total = sum(len(p.findall(text)) for p in patterns)
        if total:
            counts[kind] = total
    return counts


def _encoded_payloads(text: str) -> int:
    """Count base64-looking blobs that decode to text which itself trips another detector."""
    hits = 0
    for blob in _BASE64_BLOB.findall(text):
        try:
            decoded = base64.b64decode(blob + "=" * (-len(blob) % 4), validate=True).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError):
            continue
        if _count_by_kind(_collapse_whitespace(_normalise(decoded))):
            hits += 1
    return hits


def detect(text: str) -> InjectionResult:
    """Scan `text` for injection attempts and report what was found, by kind."""
    spaced = _normalise(text)
    normalised = _collapse_whitespace(spaced)
    # Joined before whitespace is collapsed, so a run of spaces still marks a word break ("i g n   a l l").
    joined = _collapse_whitespace(_SPACED_LETTERS.sub(lambda m: m.group().replace(" ", ""), spaced))
    counts = _count_by_kind(normalised)
    for kind, count in _count_by_kind(joined).items():
        counts[kind] = max(counts.get(kind, 0), count)
    if encoded := _encoded_payloads(normalised):
        counts[InjectionKind.ENCODED_PAYLOAD] = encoded
    return InjectionResult(findings=tuple(Finding(kind=k, count=c) for k, c in sorted(counts.items())))
