from datetime import timedelta

import pytest

from ombuds.features.claims_triage.verticals.airline.evidence_schema import (
    DisruptionType,
    FlightDisruption,
    Reroute,
)
from ombuds.features.claims_triage.verticals.airline.rules import Reason, base_compensation_eur, evaluate


def disruption(**overrides) -> FlightDisruption:
    """Baseline: in-scope 1200 km intra-EU cancellation with no notice — eligible for EUR 250."""
    fields = dict(
        disruption=DisruptionType.CANCELLATION,
        distance_km=1200,
        intra_eu=True,
        departs_from_eu=True,
        arrives_in_eu=True,
        eu_carrier=True,
    )
    return FlightDisruption(**(fields | overrides))


@pytest.mark.parametrize(
    ("distance_km", "intra_eu", "expected"),
    [
        (1500, False, 250),
        (1501, False, 400),
        (3500, False, 400),
        (3501, False, 600),
        (3501, True, 400),  # intra-EU flights cap at the medium tier
    ],
)
def test_distance_tiers(distance_km: float, intra_eu: bool, expected: int) -> None:
    assert base_compensation_eur(distance_km, intra_eu) == expected


def test_baseline_cancellation_is_eligible() -> None:
    result = evaluate(disruption())
    assert result.eligible
    assert result.compensation_eur == 250
    assert result.reasons == (Reason.ELIGIBLE,)


def test_non_eu_carrier_arriving_in_eu_is_out_of_scope() -> None:
    result = evaluate(disruption(departs_from_eu=False, eu_carrier=False))
    assert not result.eligible
    assert result.reasons == (Reason.OUT_OF_SCOPE,)


def test_eu_carrier_arriving_in_eu_is_in_scope() -> None:
    assert evaluate(disruption(departs_from_eu=False)).eligible


def test_extraordinary_circumstances_exempt() -> None:
    result = evaluate(disruption(extraordinary_circumstances=True))
    assert result.reasons == (Reason.EXTRAORDINARY_CIRCUMSTANCES,)
    assert result.compensation_eur == 0


@pytest.mark.parametrize(("hours", "eligible"), [(2.99, False), (3, True)])
def test_delay_threshold_is_three_hours(hours: float, eligible: bool) -> None:
    d = disruption(disruption=DisruptionType.DELAY, arrival_delay=timedelta(hours=hours))
    assert evaluate(d).eligible is eligible


def test_delay_is_never_reduced_by_reroute() -> None:
    d = disruption(
        disruption=DisruptionType.DELAY,
        arrival_delay=timedelta(hours=4),
        reroute=Reroute(departure_shift=timedelta(0), arrival_delay=timedelta(hours=1)),
    )
    assert evaluate(d).compensation_eur == 250


def test_fourteen_days_notice_exempts() -> None:
    result = evaluate(disruption(notice_given=timedelta(days=14)))
    assert result.reasons == (Reason.NOTICE_14_DAYS,)


@pytest.mark.parametrize(
    ("notice_days", "departure_shift_h", "arrival_delay_h", "exempt"),
    [
        (7, -2, 4, True),  # 7–13 days: up to 2 h earlier, 4 h later
        (7, -2.5, 4, False),
        (7, -2, 4.5, False),
        (6, -1, 2, True),  # < 7 days: up to 1 h earlier, 2 h later
        (6, -1.5, 2, False),
        (6, -1, 2.5, False),
    ],
)
def test_short_notice_exemption_depends_on_reroute(
    notice_days: int, departure_shift_h: float, arrival_delay_h: float, exempt: bool
) -> None:
    d = disruption(
        notice_given=timedelta(days=notice_days),
        reroute=Reroute(
            departure_shift=timedelta(hours=departure_shift_h), arrival_delay=timedelta(hours=arrival_delay_h)
        ),
    )
    assert evaluate(d).eligible is not exempt


def test_short_notice_without_reroute_is_eligible() -> None:
    assert evaluate(disruption(notice_given=timedelta(days=10))).eligible


@pytest.mark.parametrize(
    ("distance_km", "arrival_delay_h", "expected"),
    [
        (1200, 2, 125),
        (1200, 2.5, 250),
        (2000, 3, 200),
        (5000, 4, 300),
        (5000, 4.5, 600),
    ],
)
def test_reroute_halves_compensation_within_window(distance_km: float, arrival_delay_h: float, expected: int) -> None:
    d = disruption(
        distance_km=distance_km,
        intra_eu=False,
        reroute=Reroute(departure_shift=timedelta(hours=-3), arrival_delay=timedelta(hours=arrival_delay_h)),
    )
    result = evaluate(d)
    assert result.compensation_eur == expected
    assert (Reason.REROUTE_REDUCTION in result.reasons) is (expected < base_compensation_eur(distance_km, False))


def test_denied_boarding_is_eligible() -> None:
    assert evaluate(disruption(disruption=DisruptionType.DENIED_BOARDING)).compensation_eur == 250
