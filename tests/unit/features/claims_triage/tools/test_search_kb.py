import pytest

from ombuds.domain.errors import ToolExecutionError
from ombuds.features.claims_triage.tools.search_kb import SEARCH_KB_TOOL, SearchKbArgs, search_kb


def test_search_kb_raises_tool_execution_error_since_retrieval_is_not_implemented() -> None:
    """Retrieval isn't implemented yet — this must surface as ToolExecutionError, not fabricate hits or
    crash the triage turn with NotImplementedError (see ToolRegistry.dispatch)."""
    with pytest.raises(ToolExecutionError, match="not implemented"):
        search_kb(SearchKbArgs(query="baggage delay compensation"))


def test_search_kb_args_requires_nonempty_query() -> None:
    with pytest.raises(ValueError):
        SearchKbArgs(query="")


def test_tool_definition_args_model_is_search_kb_args() -> None:
    assert SEARCH_KB_TOOL.args_model is SearchKbArgs
