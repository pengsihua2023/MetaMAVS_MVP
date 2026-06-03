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

    logger.info("MetaMAVS run %s finished: status=%s", run_id, final_state.get("workflow_status"))
    return final_state
