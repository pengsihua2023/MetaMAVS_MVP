"""input_manager_node: validate inputs and produce a clean sample manifest."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..schemas import validate_manifest
from ..state import MetaMAVSState, STATUS_RUNNING
from ..utils.file_utils import write_csv, write_json
from ..utils.logging_utils import get_logger

logger = get_logger("agents.input_manager")


def input_manager_node(state: MetaMAVSState) -> dict[str, Any]:
    """Validate the manifest and config-derived inputs.

    Produces a cleaned manifest CSV under ``intermediate/`` and an input
    summary. Validation errors are recorded as critical errors (which the
    router will divert to the error handler).
    """

    logger.info("Validating input manifest and sample metadata")
    config = state["config"]
    run_dir = Path(state["run_dir"])
    dry_run = state.get("dry_run", True)

    seq_type = config.get("input", {}).get("sequencing_type", "paired_end")
    remote_data = config.get("input", {}).get("remote_data", False)
    manifest_path = state["manifest_path"]

    result = validate_manifest(
        manifest_path, sequencing_type=seq_type, dry_run=dry_run, remote_data=remote_data
    )

    warnings = list(result.warnings)
    errors: list[dict[str, Any]] = []
    update: dict[str, Any] = {"workflow_status": STATUS_RUNNING}

    if not result.is_valid:
        for msg in result.errors:
            errors.append({"node": "input_manager", "severity": "critical", "message": msg})
        logger.error("Manifest validation failed with %d error(s)", len(result.errors))
        return {
            **update,
            "errors": errors,
            "warnings": warnings,
            "execution_log": ["input_manager: manifest validation FAILED"],
            "can_continue": False,
        }

    rows = [r.model_dump(mode="json") for r in result.rows]
    clean_path = write_csv(run_dir / "intermediate" / "validated_manifest.csv", rows)
    summary_path = write_json(run_dir / "intermediate" / "input_summary.json", result.summary)

    logger.info(
        "Validated %d sample(s); %d warning(s)", result.summary.get("n_samples", 0), len(warnings)
    )

    return {
        **update,
        "validated_manifest_path": str(clean_path),
        "sample_summary": result.summary,
        "input_summary": {"summary_path": str(summary_path), **result.summary},
        "warnings": warnings,
        "errors": errors,
        "execution_log": [
            f"input_manager: validated {result.summary.get('n_samples', 0)} sample(s)"
        ],
    }
