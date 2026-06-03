"""error_handler_node: classify errors and decide whether to continue."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..state import MetaMAVSState, STATUS_COMPLETED_WITH_WARNINGS, STATUS_FAILED
from ..utils.file_utils import write_json
from ..utils.logging_utils import get_logger

logger = get_logger("agents.error_handler")


def error_handler_node(state: MetaMAVSState) -> dict[str, Any]:
    """Collect and classify recorded errors; set workflow status.

    A single critical error stops the workflow (``can_continue=False``);
    otherwise the workflow is allowed to continue to a best-effort report.
    """

    errors = state.get("errors", []) or []
    run_dir = Path(state["run_dir"])

    critical = [e for e in errors if isinstance(e, dict) and e.get("severity") == "critical"]
    non_critical = [e for e in errors if e not in critical]

    can_continue = len(critical) == 0
    status = STATUS_COMPLETED_WITH_WARNINGS if can_continue else STATUS_FAILED

    error_summary = {
        "n_errors": len(errors),
        "n_critical": len(critical),
        "n_non_critical": len(non_critical),
        "critical_messages": [e.get("message", "") for e in critical],
        "can_continue": can_continue,
    }
    write_json(run_dir / "logs" / "error_summary.json", error_summary)

    logger.error(
        "Error handler: %d error(s), %d critical, can_continue=%s",
        len(errors), len(critical), can_continue,
    )

    return {
        "error_summary": error_summary,
        "can_continue": can_continue,
        "workflow_status": status,
        "execution_log": [f"error_handler: {len(critical)} critical error(s), can_continue={can_continue}"],
    }
