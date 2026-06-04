"""Tests for conditional routing logic."""

from __future__ import annotations

from metamavs.routing import (
    NODE_ERROR,
    NODE_QC,
    NODE_REPORT,
    NODE_REVIEW,
    error_handler_router,
    has_critical_error,
    make_step_router,
    review_router,
    should_request_review,
)


def _base_state(**overrides):
    state = {
        "config": {"risk": {"review_on_high_risk": True, "review_on_novel_candidates": True, "review_on_qc_failure": True}},
        "errors": [],
        "can_continue": True,
        "risk_summary": {"overall_risk": "Low"},
        "novel_candidate_summary": {"n_candidates": 0},
        "qc_pass_fail": {"s1": "pass"},
        "review_required": False,
    }
    state.update(overrides)
    return state


def test_has_critical_error_detects_severity():
    state = _base_state(errors=[{"severity": "critical", "message": "boom"}])
    assert has_critical_error(state) is True


def test_has_critical_error_detects_cannot_continue():
    assert has_critical_error(_base_state(can_continue=False)) is True


def test_no_critical_error_on_clean_state():
    assert has_critical_error(_base_state()) is False


def test_step_router_proceeds_when_clean():
    router = make_step_router(NODE_QC)
    assert router(_base_state()) == NODE_QC


def test_step_router_diverts_on_error():
    router = make_step_router(NODE_QC)
    assert router(_base_state(can_continue=False)) == NODE_ERROR


def test_review_router_sends_high_risk_to_review():
    state = _base_state(review_required=True)
    assert review_router(state) == NODE_REVIEW


def test_review_router_skips_review_when_clean():
    # No review needed -> proceed to the (optional) LLM interpretation node.
    from metamavs.routing import NODE_LLM

    assert review_router(_base_state(review_required=False)) == NODE_LLM


def test_review_router_errors_take_priority():
    state = _base_state(review_required=True, can_continue=False)
    assert review_router(state) == NODE_ERROR


def test_should_request_review_high_risk():
    state = _base_state(risk_summary={"overall_risk": "High"})
    assert should_request_review(state) is True


def test_should_request_review_critical():
    state = _base_state(risk_summary={"overall_risk": "Critical"})
    assert should_request_review(state) is True


def test_should_request_review_novel_candidates():
    state = _base_state(novel_candidate_summary={"n_candidates": 2})
    assert should_request_review(state) is True


def test_should_request_review_qc_failure():
    state = _base_state(qc_pass_fail={"s1": "fail"})
    assert should_request_review(state) is True


def test_should_not_request_review_for_clean_low_risk():
    assert should_request_review(_base_state()) is False


def test_error_handler_router_continue():
    assert error_handler_router(_base_state(can_continue=True)) == NODE_REPORT


def test_error_handler_router_stop():
    from metamavs.routing import NODE_FINAL

    assert error_handler_router(_base_state(can_continue=False)) == NODE_FINAL
