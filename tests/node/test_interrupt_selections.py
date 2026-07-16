"""Unit tests for the interruptSelections node (human-in-the-loop gate).

The node pauses the graph with `interrupt(...)`, receives the user's chosen
source ids on resume, and partitions the discovered sources into
selected / non-selected sets for the Rocchio step. `interrupt` is patched to
stand in for the value injected on resume.
"""
from unittest.mock import patch

from src.app.graph.nodes.interruptSelections import interruptSelections

MODULE = "src.app.graph.nodes.interruptSelections"


def test_comma_separated_string_is_split_and_trimmed():
    state = {"sourceIds": ["a", "b", "c"]}
    with patch(f"{MODULE}.interrupt", return_value=" a , c "):
        out = interruptSelections(state)

    assert out["selectedSourceIds"] == ["a", "c"]
    assert out["nonselectedSourceIds"] == ["b"]


def test_list_input_is_used_directly():
    state = {"sourceIds": ["a", "b", "c"]}
    with patch(f"{MODULE}.interrupt", return_value=["b"]):
        out = interruptSelections(state)

    assert out["selectedSourceIds"] == ["b"]
    assert out["nonselectedSourceIds"] == ["a", "c"]


def test_empty_selection_puts_everything_in_nonselected():
    state = {"sourceIds": ["a", "b"]}
    with patch(f"{MODULE}.interrupt", return_value=""):
        out = interruptSelections(state)

    assert out["selectedSourceIds"] == []
    assert out["nonselectedSourceIds"] == ["a", "b"]


def test_interrupt_payload_advertises_the_discovered_sources():
    state = {"sourceIds": ["x", "y"]}
    with patch(f"{MODULE}.interrupt", return_value=[]) as mock_interrupt:
        interruptSelections(state)

    (payload,), _ = mock_interrupt.call_args
    assert payload == {"type": "topic_selection", "source_ids": ["x", "y"]}
