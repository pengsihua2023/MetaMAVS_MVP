"""remote_execution_agent: stage scripts, submit the SLURM DAG, monitor to terminal."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..remote.backends import make_backend
from ..remote.job_ledger import JobLedger
from ..remote.jobgen import build_job_specs, remote_run_dir
from ..remote.slurm import poll_until_terminal, submit_dag
from ..state import MetaMAVSState
from ..utils.logging_utils import get_logger

logger = get_logger("agents.remote_execution")


def remote_execution_agent_node(state: MetaMAVSState) -> dict[str, Any]:
    """Upload scripts, submit the dependency DAG, poll until all jobs terminate."""

    logger.info("Remote execution: building job specs and submitting to HPC")
    run_dir = Path(state["run_dir"])
    hpc = state.get("config", {}).get("hpc", {}) or {}

    try:
        backend = make_backend(state)
    except Exception as exc:
        msg = f"remote_execution: cannot create backend: {exc}"
        logger.error(msg)
        return {"errors": [{"node": "remote_execution", "severity": "critical", "message": msg}],
                "can_continue": False, "warnings": [msg]}

    specs = build_job_specs(state)
    if not specs:
        warn = "remote_execution: no job specs (empty manifest?)"
        return {"warnings": [warn], "execution_log": [warn]}

    rrun = remote_run_dir(state)
    warnings: list[str] = []

    # Stage: ensure remote dirs + upload scripts (+ inputs unless already on HPC).
    backend.run(f"mkdir -p {rrun}/scripts {rrun}/work {rrun}/results {rrun}/logs")
    remote_data = state.get("config", {}).get("input", {}).get("remote_data", False)
    for spec in specs:
        if not backend.upload(spec.script_local, spec.script_remote):
            warnings.append(f"remote_execution: failed to upload {spec.job_name} script")
        if not remote_data:
            for f in spec.input_files:
                backend.upload(f, f"{rrun}/inputs/{Path(f).name}")

    # Submit DAG + record ids to the durable ledger.
    ledger = JobLedger(run_dir)
    try:
        name_to_id = submit_dag(backend, specs)
    except Exception as exc:
        msg = f"remote_execution: sbatch failed: {exc}"
        logger.error(msg)
        return {"errors": [{"node": "remote_execution", "severity": "critical", "message": msg}],
                "can_continue": False, "warnings": warnings + [msg]}
    ledger.record_ids(name_to_id)

    # Monitor until terminal, updating the ledger each round.
    result = poll_until_terminal(
        backend, name_to_id, state["run_id"],
        interval_s=int(hpc.get("poll_interval_s", 30)),
        max_wait_s=int(hpc.get("max_wait_s", 86400)),
        on_update=ledger.update_statuses,
    )

    if result.failed:
        warnings.append(f"remote_execution: {len(result.failed)} job(s) did not succeed: {', '.join(result.failed)}")
    logger.info("Remote execution done: all_ok=%s failed=%s", result.all_ok, result.failed)

    return {
        "remote_job_specs": [s.model_dump() for s in specs],
        "remote_execution_result": result.model_dump(),
        "execution_reports": [{"step": "remote_execution", "mode": "hpc",
                               "n_jobs": len(specs), "failed": result.failed}],
        "warnings": warnings,
        "execution_log": [f"remote_execution: {len(specs)} job(s), all_ok={result.all_ok}"],
    }
