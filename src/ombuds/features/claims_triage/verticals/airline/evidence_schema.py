"""Evidence schema: the facts a claim must establish before EU261 rules can be evaluated."""

from datetime import timedelta
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class DisruptionType(StrEnum):
    DELAY = "delay"
    CANCELLATION = "cancellation"
    DENIED_BOARDING = "denied_boarding"


class Reroute(BaseModel):
    """Alternative flight offered, relative to the original schedule. Negative departure shift = earlier."""

    model_config = ConfigDict(frozen=True)

    departure_shift: timedelta
    arrival_delay: timedelta


class FlightDisruption(BaseModel):
    """Facts needed to decide EU261 eligibility. Every field is a fact, never a judgment."""

    model_config = ConfigDict(frozen=True)

    disruption: DisruptionType
    distance_km: float = Field(gt=0)
    intra_eu: bool
    departs_from_eu: bool
    arrives_in_eu: bool
    eu_carrier: bool
    arrival_delay: timedelta = timedelta(0)
    notice_given: timedelta | None = Field(
        default=None, description="Cancellations only: how far ahead passengers were told"
    )
    reroute: Reroute | None = None
    extraordinary_circumstances: bool = False
