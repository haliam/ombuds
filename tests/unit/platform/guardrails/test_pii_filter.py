from pathlib import Path

import pytest

from ombuds.platform.guardrails.pii_filter import Finding, PiiKind, redact, redact_value

_KB_SEED = Path(__file__).parents[4] / "src/ombuds/features/claims_triage/verticals/airline/kb_seed"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("write to jane.doe+claims@example.co.uk please", "write to [EMAIL] please"),
        ("IBAN DE89 3704 0044 0532 0130 00 thanks", "IBAN [IBAN] thanks"),
        ("IBAN DE89370400440532013000.", "IBAN [IBAN]."),
        ("pay GB82 WEST 1234 5698 7654 32", "pay [IBAN]"),
        ("card 4111 1111 1111 1111 was charged", "card [CARD] was charged"),
        ("card 4111-1111-1111-1111", "card [CARD]"),
        ("call +49 30 1234 5678 anytime", "call [PHONE] anytime"),
        ("call 0044 20 7946 0958", "call [PHONE]"),
        ("call (555) 123-4567", "call [PHONE]"),
        ("call 030 1234 5678", "call [PHONE]"),
        ("my passport number: X1234567", "my passport number: [PASSPORT]"),
        ("Passport C01X00T47 attached", "Passport [PASSPORT] attached"),
        ("booking reference is AB12CD", "booking reference is [BOOKING_REF]"),
        ("PNR: XYZABC", "PNR: [BOOKING_REF]"),
        ("my reservation code K7P2QW was cancelled", "my reservation code [BOOKING_REF] was cancelled"),
    ],
)
def test_redacts_each_kind_with_a_typed_placeholder(text: str, expected: str) -> None:
    assert redact(text).text == expected


def test_an_iban_followed_by_an_uppercase_word_still_redacts_only_the_iban() -> None:
    assert redact("IBAN DE89 3704 0044 0532 0130 00 THE END").text == "IBAN [IBAN] THE END"


@pytest.mark.parametrize(
    "text",
    [
        "card 4111 1111 1111 1112",  # fails Luhn
        "passport control took two hours",  # keyword but no identifier
        "my booking number was lost",  # keyword followed by an ordinary word
        "BOOKING NUMBER",  # the placeholder-looking words are excluded
    ],
)
def test_a_candidate_that_fails_its_check_is_left_untouched(text: str) -> None:
    assert redact(text).text == text


def test_an_iban_failing_mod_97_is_not_reported_as_an_iban() -> None:
    # Its digit runs may still be caught as a phone or card number: over-redacting is the safe direction.
    result = redact("IBAN DE89 3704 0044 0532 0130 02")

    assert PiiKind.IBAN not in {finding.kind for finding in result.findings}


@pytest.mark.parametrize(
    "text",
    [
        "Flight LH1234 from FRA to JFK departed 14:30 and landed at 19:05.",
        "The flight is 3,500 km, a delay of 4 hours 12 minutes on 2026-10-08.",
        "Delayed 03/10/2026 by 180 minutes; compensation of EUR 600 applies.",
        "Flights over 3500 km but not intra-EU pay EUR 600 (Art. 7(1)(c)).",
        "Booked as LH1234 with reference LH5678 on the schedule.",  # no booking keyword, so not a PNR
        "Arrived 3 h 45 m late after a 2,345 km flight, ticket 1234 5678.",
    ],
)
def test_flight_facts_pass_through_unchanged(text: str) -> None:
    result = redact(text)

    assert result.text == text
    assert result.findings == ()


@pytest.mark.parametrize("path", sorted(_KB_SEED.glob("*.md")), ids=lambda path: path.name)
def test_the_knowledge_base_seed_passes_through_unchanged(path: Path) -> None:
    text = path.read_text()

    assert redact(text).text == text


def test_findings_count_each_kind_and_never_carry_the_values() -> None:
    result = redact("a@b.com, c@d.org and call +49 30 1234 5678")

    assert set(result.findings) == {Finding(kind=PiiKind.EMAIL, count=2), Finding(kind=PiiKind.PHONE, count=1)}
    assert "a@b.com" not in result.model_dump_json()


def test_clean_text_has_no_findings() -> None:
    assert redact("My flight was cancelled.").findings == ()


@pytest.mark.parametrize(
    "text",
    [
        "mail jane@example.com, IBAN DE89 3704 0044 0532 0130 00, card 4111 1111 1111 1111",
        "passport X1234567, booking AB12CD, call +49 30 1234 5678",
        "nothing sensitive here",
    ],
)
def test_redaction_is_idempotent(text: str) -> None:
    once = redact(text)

    assert redact(once.text).text == once.text
    assert redact(once.text).findings == ()


def test_a_card_is_not_also_reported_as_a_phone_number() -> None:
    result = redact("card 4111 1111 1111 1111")

    assert result.findings == (Finding(kind=PiiKind.CARD, count=1),)


def test_redact_value_redacts_strings_at_any_depth_and_leaves_other_types_alone() -> None:
    value = {"query": "mail a@b.com", "nested": {"items": ["call +49 30 1234 5678", 3, None, True]}, "top_k": 5}

    assert redact_value(value) == {
        "query": "mail [EMAIL]",
        "nested": {"items": ["call [PHONE]", 3, None, True]},
        "top_k": 5,
    }
