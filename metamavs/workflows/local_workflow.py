"""Local execution backend.

Drives the compiled LangGraph from an initial state to completion using an
in-memory checkpointer scoped to the run id.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ..config import MetaMAVSConfig
from ..graph import compile_graph
from ..state import MetaMAVSState, create_initial_state
from ..utils.file_utils import ensure_run_dir, run_id_from_timestamp
from ..utils.logging_utils import get_logger, setup_logging

logger = get_logger("workflows.local")


def run_local_workflow(
    config: MetaMAVSConfig,
    *,
    config_path: str | None = None,
    dry_run: bool | None = None,
    run_id: str | None = None,
) -> MetaMAVSState:
    """Execute the full MetaMAVS workflow locally and return the final state.

    Parameters
    ----------
    config:
        Validated configuration object.
    config_path:
        Original config path (recorded in the report for reproducibility).
    dry_run:
        Override the config's dry-run flag if provided.
    run_id:
        Optional explicit run id (defaults to a timestamp-based id).
    """

    effective_dry_run = config.execution.dry_run if dry_run is None else dry_run
    run_id = run_id or run_id_from_timestamp()
    run_dir = ensure_run_dir(config.project.output_dir)

    setup_logging(level=logging.INFO, log_file=run_dir / "logs" / "metamavs.log")
    logger.info("Starting MetaMAVS run %s (dry_run=%s)", run_id, effective_dry_run)

    config_dict: dict[str, Any] = config.model_dump(mode="json")
    config_dict["_config_path"] = config_path or ""

    initial_state = create_initial_state(
        config=config_dict,
        run_id=run_id,
        run_dir=str(run_dir),
        manifest_path=config.input.manifest,
        dry_run=effective_dry_run,
    )

    app = compile_graph()
    thread_config = {"configurable": {"thread_id": run_id}, "recursion_limit": 50}
    final_state = app.invoke(initial_state, config=thread_config)

    # Paused for human-in-the-loop review: persist a resumable snapshot.
    if final_state.get("awaiting_review"):
        from ..utils.file_utils import write_json

        write_json(run_dir / "paused_state.json", dict(final_state))
        logger.info("MetaMAVS run %s PAUSED for human review (run: metamavs review --run-dir %s)",
                    run_id, run_dir)
        return final_state

    logger.info("MetaMAVS run %s finished: status=%s", run_id, final_state.get("workflow_status"))
    return final_state


# Cross-cutting accumulator fields that should be appended (not replaced) on merge.
_ACCUM = {"warnings", "errors", "execution_log", "execution_reports",
          "remote_job_specs", "parse_results"}


def _merge(state: dict, partial: dict) -> None:
    for k, v in partial.items():
        if k in _ACCUM and isinstance(v, list):
            state[k] = (state.get(k) or []) + v
        else:
            state[k] = v


def load_pending_review(run_dir: str | Path) -> dict[str, Any] | None:
    """Load a paused run's state, or None if not awaiting review."""

    import json

    p = Path(run_dir) / "paused_state.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def resume_after_review(run_dir: str | Path, *, approved: bool, notes: str = "") -> MetaMAVSState:
    """Apply a human review decision to a paused run and finish it.

    Approved → run interpretation + report + final summary. Rejected → finalize
    without a report. Removes the pause marker on completion.
    """

    from ..agents import (
        final_summary_node,
        llm_interpretation_agent_node,
        report_writer_agent_node,
    )
    from ..utils.file_utils import write_json

    run_dir = Path(run_dir)
    state = load_pending_review(run_dir)
    if state is None:
        raise FileNotFoundError(f"No paused run awaiting review in {run_dir}")

    setup_logging(level=logging.INFO, log_file=run_dir / "logs" / "metamavs.log")
    decision = "approved" if approved else "rejected"
    state["review_decision"] = decision
    state["reviewer_notes"] = notes or f"Human reviewer decision: {decision}"
    state["approved_for_report"] = approved
    state["awaiting_review"] = False
    write_json(run_dir / "intermediate" / "human_review.json",
               {"decision": decision, "approved": approved, "notes": state["reviewer_notes"]})
    logger.info("Resuming run %s after human review: %s", state.get("run_id"), decision)

    if approved:
        for node in (llm_interpretation_agent_node, report_writer_agent_node, final_summary_node):
            _merge(state, node(state))
    else:
        _merge(state, final_summary_node(state))
        state["workflow_status"] = "rejected_by_reviewer"

    (run_dir / "paused_state.json").unlink(missing_ok=True)
    return state
