"""final_summary_node: produce a concise end-of-run summary."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..state import MetaMAVSState, STATUS_COMPLETED, STATUS_COMPLETED_WITH_WARNINGS, STATUS_FAILED
from ..utils.file_utils import write_json
from ..utils.logging_utils import get_logger

logger = get_logger("agents.final_summary")


def final_summary_node(state: MetaMAVSState) -> dict[str, Any]:
    """Summarise the run: status, report paths, key risks and warnings."""

    logger.info("Building final run summary")
    run_dir = Path(state["run_dir"])

    errors = state.get("errors", []) or []
    warnings = state.get("warnings", []) or []
    risk = state.get("risk_summary", {}) or {}

    # Preserve a failed status set by the error handler; otherwise derive it.
    status = state.get("workflow_status", "")
    if status not in {STATUS_FAILED, STATUS_COMPLETED_WITH_WARNINGS}:
        status = STATUS_COMPLETED_WITH_WARNINGS if warnings else STATUS_COMPLETED

    high_risk = [
        r["taxon_name"]
        for r in risk.get("top_risks", [])
        if r.get("risk_level") in {"High", "Critical"}
    ]

    final_summary = {
        "status": status,
        "run_id": state.get("run_id", ""),
        "run_dir": str(run_dir),
        "overall_risk": risk.get("overall_risk", "Low"),
        "high_risk_detections": high_risk,
        "n_warnings": len(warnings),
        "n_errors": len(errors),
        "markdown_report": state.get("markdown_report_path"),
        "html_report": state.get("html_report_path"),
        "review_decision": state.get("review_decision"),
    }

    # Persist the complete final state alongside the summary.
    write_json(run_dir / "state.json", {k: v for k, v in state.items() if k != "config"} | {"config": state.get("config", {})})
    write_json(run_dir / "logs" / "final_summary.json", final_summary)

    logger.info("Run %s complete: status=%s, overall_risk=%s", final_summary["run_id"], status, final_summary["overall_risk"])

    return {
        "final_summary": final_summary,
        "workflow_status": status,
        "execution_log": [f"final_summary: status={status}"],
    }
