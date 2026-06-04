"""Conditional routing functions for the MetaMAVS LangGraph.

These pure functions inspect the shared state and return the *name* of the next
node. Keeping them separate from ``graph.py`` makes the routing logic trivially
unit-testable without compiling the graph.
"""

from __future__ import annotations

from typing import Callable

from .state import MetaMAVSState

# Node-name constants (single source of truth shared with graph.py).
NODE_INPUT = "input_manager"
NODE_QC = "qc_agent"
NODE_HOST = "host_removal_agent"
NODE_VIRAL = "viral_detection_agent"
NODE_TAXONOMY = "taxonomy_agent"
NODE_ABUNDANCE = "abundance_agent"
NODE_NOVEL = "novel_virus_agent"
NODE_RISK = "risk_assessment_agent"
NODE_REVIEW = "human_review"
NODE_REPORT = "report_writer_agent"
NODE_FINAL = "final_summary"
NODE_ERROR = "error_handler"
# Phase 3 remote (HPC) nodes.
NODE_REMOTE_EXEC = "remote_execution_agent"
NODE_RESULT_SYNC = "result_sync_agent"
NODE_PARSER = "tool_output_parser_agent"


def has_critical_error(state: MetaMAVSState) -> bool:
    """Return True if the state holds an unrecoverable error.

    A critical error is any recorded error with ``severity == "critical"`` or
    an explicit ``can_continue == False`` flag.
    """

    if state.get("can_continue") is False:
        return True
    for err in state.get("errors", []) or []:
        if isinstance(err, dict) and err.get("severity") == "critical":
            return True
    return False


def make_step_router(next_node: str) -> Callable[[MetaMAVSState], str]:
    """Build a router that proceeds to *next_node* unless a critical error exists.

    Used for the linear backbone: every processing node gets a conditional edge
    that diverts to the error handler when something critical happened.
    """

    def _route(state: MetaMAVSState) -> str:
        if has_critical_error(state):
            return NODE_ERROR
        return next_node

    _route.__name__ = f"route_to_{next_node}"
    return _route


def mode_router(state: MetaMAVSState) -> str:
    """After the command-builder agents, route on ``execution.mode``.

    ``hpc`` → run the remote stage (remote_execution → result_sync → parser);
    otherwise (local/dry-run) → straight to taxonomy on the already-produced
    tables.
    """

    if has_critical_error(state):
        return NODE_ERROR
    mode = (state.get("config", {}).get("execution", {}) or {}).get("mode", "local")
    return NODE_REMOTE_EXEC if mode == "hpc" else NODE_TAXONOMY


def review_router(state: MetaMAVSState) -> str:
    """Decide whether human review is required after risk assessment.

    Routes to :data:`NODE_REVIEW` when any review trigger fires, to
    :data:`NODE_ERROR` on a critical error, otherwise straight to the report
    writer.
    """

    if has_critical_error(state):
        return NODE_ERROR
    if state.get("review_required"):
        return NODE_REVIEW
    return NODE_REPORT


def error_handler_router(state: MetaMAVSState) -> str:
    """After the error handler, either continue to the report or finalise.

    If the handler decided the workflow can still continue we attempt a
    best-effort report; otherwise we jump to the final summary which will
    record the failed status.
    """

    if state.get("can_continue"):
        return NODE_REPORT
    return NODE_FINAL


def should_request_review(state: MetaMAVSState) -> bool:
    """Pure predicate used by the risk agent to set ``review_required``.

    Triggers (any of):
      * a High/Critical overall risk level;
      * one or more novel virus candidates;
      * a QC failure for any sample;
      * the presence of critical warnings flagged by upstream agents.
    """

    config = state.get("config", {}) or {}
    risk_cfg = config.get("risk", {}) or {}

    risk_summary = state.get("risk_summary", {}) or {}
    overall = str(risk_summary.get("overall_risk", "Low")).lower()
    if risk_cfg.get("review_on_high_risk", True) and overall in {"high", "critical"}:
        return True

    novel = state.get("novel_candidate_summary", {}) or {}
    if risk_cfg.get("review_on_novel_candidates", True) and int(novel.get("n_candidates", 0)) > 0:
        return True

    qc = state.get("qc_pass_fail", {}) or {}
    if risk_cfg.get("review_on_qc_failure", True) and any(
        str(v).lower() == "fail" for v in qc.values()
    ):
        return True

    return False
