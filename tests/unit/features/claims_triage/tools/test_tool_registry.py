from ombuds.features.claims_triage.tools import build_tool_registry
from ombuds.features.claims_triage.tools.check_eligibility import CHECK_ELIGIBILITY_TOOL
from ombuds.features.claims_triage.tools.issue_payment import ISSUE_PAYMENT_TOOL
from ombuds.features.claims_triage.tools.log_claim import LOG_CLAIM_TOOL
from ombuds.features.claims_triage.tools.search_kb import SEARCH_KB_TOOL


def test_build_tool_registry_registers_exactly_the_four_claims_triage_tools() -> None:
    registry = build_tool_registry()

    definitions = registry.definitions()

    assert {d.name for d in definitions} == {
        SEARCH_KB_TOOL.name,
        CHECK_ELIGIBILITY_TOOL.name,
        LOG_CLAIM_TOOL.name,
        ISSUE_PAYMENT_TOOL.name,
    }
