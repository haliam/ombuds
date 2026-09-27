from ombuds.features.claims_triage.tools import build_tool_registry
from ombuds.features.claims_triage.tools.check_eligibility import CHECK_ELIGIBILITY_TOOL
from ombuds.features.claims_triage.tools.log_claim import LOG_CLAIM_TOOL


def test_build_tool_registry_registers_exactly_check_eligibility_and_log_claim() -> None:
    registry = build_tool_registry()

    definitions = registry.definitions()

    assert {d.name for d in definitions} == {CHECK_ELIGIBILITY_TOOL.name, LOG_CLAIM_TOOL.name}
