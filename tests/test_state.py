"""Tests for state construction and reducer-based accumulation."""

from __future__ import annotations

import operator
from typing import Annotated, get_type_hints

from metamavs.state import (
    STATUS_PENDING,
    MetaMAVSState,
    create_initial_state,
)


def _make_state():
    return create_initial_state(
        config={"project": {"name": "MetaMAVS"}},
        run_id="run_test",
        run_dir="/tmp/run_test",
        manifest_path="data/example_manifest.csv",
        dry_run=True,
    )


def test_initial_state_defaults():
    state = _make_state()
    assert state["run_id"] == "run_test"
    assert state["dry_run"] is True
    assert state["workflow_status"] == STATUS_PENDING
    assert state["can_continue"] is True
    assert state["warnings"] == []
    assert state["errors"] == []
    assert state["execution_log"] == []
    assert state["review_required"] is False


def test_accumulator_fields_use_add_reducer():
    # The annotated reducer is what lets nodes append rather than overwrite.
    hints = get_type_hints(MetaMAVSState, include_extras=True)
    for field in ("warnings", "errors", "execution_log"):
        meta = getattr(hints[field], "__metadata__", ())
        assert operator.add in meta, f"{field} should use operator.add reducer"


def test_partial_update_shape_is_dict():
    state = _make_state()
    # Nodes return plain dicts; simulate a merge for accumulators.
    update = {"warnings": ["w1"], "execution_log": ["step1"]}
    merged_warnings = state["warnings"] + update["warnings"]
    assert merged_warnings == ["w1"]
