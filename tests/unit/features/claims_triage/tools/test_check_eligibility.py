from ombuds.features.claims_triage.tools.check_eligibility import CHECK_ELIGIBILITY_TOOL, check_eligibility
from ombuds.features.claims_triage.verticals.airline.evidence_schema import DisruptionType, FlightDisruption
from ombuds.features.claims_triage.verticals.airline.rules import Reason


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


def test_check_eligibility_delegates_to_rules_evaluate() -> None:
    result = check_eligibility(disruption())

    assert result.eligible is True
    assert result.compensation_eur == 250
    assert result.reasons == (Reason.ELIGIBLE,)


def test_check_eligibility_reports_out_of_scope() -> None:
    result = check_eligibility(disruption(departs_from_eu=False, arrives_in_eu=False))

    assert result.eligible is False
    assert result.reasons == (Reason.OUT_OF_SCOPE,)


def test_tool_definition_args_model_matches_flight_disruption() -> None:
    assert CHECK_ELIGIBILITY_TOOL.args_model is FlightDisruption
    schema = CHECK_ELIGIBILITY_TOOL.input_schema()
    properties = schema["properties"]
    assert isinstance(properties, dict)
    assert "distance_km" in properties
