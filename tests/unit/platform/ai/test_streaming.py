import json

import pytest

from ombuds.platform.ai.streaming import JSONBuffer


def test_json_buffer_assembles_fragments_into_one_object() -> None:
    buffer = JSONBuffer()
    buffer.append("call-1", '{"disru')
    buffer.append("call-1", 'ption": "cancel')
    buffer.append("call-1", 'lation"}')

    assert buffer.finalize("call-1") == {"disruption": "cancellation"}


def test_json_buffer_returns_empty_dict_for_a_call_with_no_fragments() -> None:
    buffer = JSONBuffer()

    assert buffer.finalize("never-appended") == {}


def test_json_buffer_discards_fragments_after_finalize() -> None:
    buffer = JSONBuffer()
    buffer.append("call-1", "{}")
    buffer.finalize("call-1")

    assert buffer.finalize("call-1") == {}


def test_json_buffer_tracks_calls_independently() -> None:
    buffer = JSONBuffer()
    buffer.append("call-1", '{"a": 1}')
    buffer.append("call-2", '{"b": 2}')

    assert buffer.finalize("call-1") == {"a": 1}
    assert buffer.finalize("call-2") == {"b": 2}


def test_json_buffer_raises_json_decode_error_on_malformed_json() -> None:
    buffer = JSONBuffer()
    buffer.append("call-1", "{not json")

    with pytest.raises(json.JSONDecodeError):
        buffer.finalize("call-1")


def test_json_buffer_raises_value_error_when_json_is_not_an_object() -> None:
    buffer = JSONBuffer()
    buffer.append("call-1", "[1, 2, 3]")

    with pytest.raises(ValueError, match="did not parse to a JSON object"):
        buffer.finalize("call-1")
