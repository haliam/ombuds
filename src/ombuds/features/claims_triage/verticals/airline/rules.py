"""EU261 eligibility logic.

Deterministic implementation of a deliberately simplified subset of Regulation (EC) 261/2004:
- Scope (Art. 3): departure from an EU airport, or arrival in the EU on an EU carrier.
- Compensation tiers (Art. 7(1)): EUR 250 / 400 / 600 by great-circle distance.
- 50% reduction when a reroute lands within 2/3/4 h of the original arrival (Art. 7(2)).
- Cancellation notice exemptions (Art. 5(1)(c)).
- Extraordinary circumstances exemption (Art. 5(3)).
- Long delay treated as cancellation for compensation at >= 3 h arrival delay (CJEU, Sturgeon, C-402/07).

Not modelled: voluntary denied boarding, missed connections across bookings, care/assistance rights,
non-EU equivalents (UK261). The LLM may ask for this result; it never computes it.
"""

from datetime import timedelta
from enum import StrEnum

from ombuds.domain.models.claim import EligibilityResult
from ombuds.features.claims_triage.verticals.airline.evidence_schema import (
    DisruptionType,
    FlightDisruption,
    Reroute,
)

SHORT_HAUL_MAX_KM = 1500
MEDIUM_HAUL_MAX_KM = 3500

COMPENSATION_SHORT_EUR = 250
COMPENSATION_MEDIUM_EUR = 400
COMPENSATION_LONG_EUR = 600

MIN_COMPENSABLE_DELAY = timedelta(hours=3)

FULL_NOTICE = timedelta(days=14)
PARTIAL_NOTICE = timedelta(days=7)


class Reason(StrEnum):
    OUT_OF_SCOPE = "out_of_scope"
    EXTRAORDINARY_CIRCUMSTANCES = "extraordinary_circumstances"
    DELAY_BELOW_THRESHOLD = "delay_below_threshold"
    NOTICE_14_DAYS = "notice_14_days_or_more"
    NOTICE_WITH_ACCEPTABLE_REROUTE = "notice_with_acceptable_reroute"
    REROUTE_REDUCTION = "reroute_within_art_7_2_reduction"
    ELIGIBLE = "eligible"


def in_scope(d: FlightDisruption) -> bool:
    """Art. 3: departs from the EU, or arrives in the EU on an EU carrier."""
    return d.departs_from_eu or (d.arrives_in_eu and d.eu_carrier)


def base_compensation_eur(distance_km: float, intra_eu: bool) -> int:
    """Art. 7(1) amount before any reroute reduction. Intra-EU flights over 1500 km cap at the medium tier."""
    if distance_km <= SHORT_HAUL_MAX_KM:
        return COMPENSATION_SHORT_EUR
    if distance_km <= MEDIUM_HAUL_MAX_KM or intra_eu:
        return COMPENSATION_MEDIUM_EUR
    return COMPENSATION_LONG_EUR


def _reroute_reduction_window(distance_km: float) -> timedelta:
    if distance_km <= SHORT_HAUL_MAX_KM:
        return timedelta(hours=2)
    if distance_km <= MEDIUM_HAUL_MAX_KM:
        return timedelta(hours=3)
    return timedelta(hours=4)


def _cancellation_exempt_by_notice(notice: timedelta | None, reroute: Reroute | None) -> Reason | None:
    if notice is None:
        return None
    if notice >= FULL_NOTICE:
        return Reason.NOTICE_14_DAYS
    if reroute is None:
        return None
    if notice >= PARTIAL_NOTICE:
        max_early, max_late = timedelta(hours=2), timedelta(hours=4)
    else:
        max_early, max_late = timedelta(hours=1), timedelta(hours=2)
    if reroute.departure_shift >= -max_early and reroute.arrival_delay <= max_late:
        return Reason.NOTICE_WITH_ACCEPTABLE_REROUTE
    return None


def _ineligible(reason: Reason) -> EligibilityResult:
    return EligibilityResult(eligible=False, compensation_eur=0, reasons=(reason,))


def evaluate(d: FlightDisruption) -> EligibilityResult:
    """Decide EU261 eligibility and compensation for one disrupted flight.

    Checks run in order and the first exemption found wins, so the returned reason is the most
    fundamental one: a flight outside EU261 scope is reported as out of scope, not as weather-exempt.
    """
    if not in_scope(d):
        return _ineligible(Reason.OUT_OF_SCOPE)
    if d.extraordinary_circumstances:
        return _ineligible(Reason.EXTRAORDINARY_CIRCUMSTANCES)
    if d.disruption is DisruptionType.DELAY and d.arrival_delay < MIN_COMPENSABLE_DELAY:
        return _ineligible(Reason.DELAY_BELOW_THRESHOLD)
    if d.disruption is DisruptionType.CANCELLATION:
        exemption = _cancellation_exempt_by_notice(d.notice_given, d.reroute)
        if exemption is not None:
            return _ineligible(exemption)

    amount = base_compensation_eur(d.distance_km, d.intra_eu)
    reasons: tuple[str, ...] = (Reason.ELIGIBLE,)
    # Art. 7(2) applies to re-routing, which only exists for cancellations and denied boarding.
    if (
        d.disruption is not DisruptionType.DELAY
        and d.reroute is not None
        and d.reroute.arrival_delay <= _reroute_reduction_window(d.distance_km)
    ):
        amount //= 2
        reasons += (Reason.REROUTE_REDUCTION,)
    return EligibilityResult(eligible=True, compensation_eur=amount, reasons=reasons)
