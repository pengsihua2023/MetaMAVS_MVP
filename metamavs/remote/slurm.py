"""SLURM helpers: script rendering, sbatch command, sacct parsing, DAG + polling."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from ..utils.logging_utils import get_logger
from .types import RemoteExecutionResult, RemoteJobSpec, SlurmJobStatus

if TYPE_CHECKING:  # avoid import cycle (backends imports slurm)
    from .backends import RemoteBackend

logger = get_logger("remote.slurm")


def render_job_script(spec: RemoteJobSpec, log_dir: str) -> str:
    """Render a self-contained #SBATCH bash script for one job."""

    r = spec.resources
    lines = [
        "#!/usr/bin/env bash",
        f"#SBATCH --job-name={spec.job_name}",
        f"#SBATCH --partition={r.partition}",
        f"#SBATCH --cpus-per-task={r.cpus}",
        f"#SBATCH --mem={r.mem}",
        f"#SBATCH --time={r.time}",
        f"#SBATCH --output={log_dir}/{spec.job_name}_%j.out",
        f"#SBATCH --error={log_dir}/{spec.job_name}_%j.err",
        "",
        "set -euo pipefail",
        "",
    ]
    for mod in spec.modules:
        lines.append(f"module load {mod}")
    if spec.conda_env:
        lines.append(f"conda activate {spec.conda_env}")
    if spec.modules or spec.conda_env:
        lines.append("")
    lines += list(spec.payload) + [""]
    return "\n".join(lines)


def build_sbatch_command(script_remote: str, dep_job_ids: list[str]) -> str:
    """Build an `sbatch --parsable` command, chaining afterok dependencies."""

    dep = f"--dependency=afterok:{':'.join(dep_job_ids)} " if dep_job_ids else ""
    return f"sbatch --parsable {dep}{script_remote}"


def parse_sacct(text: str) -> list[SlurmJobStatus]:
    """Parse `sacct --parsable2 --noheader --format=JobID,JobName,State,ExitCode`.

    Sub-steps like ``<id>.batch`` are ignored; only the primary job line is kept.
    """

    out: list[SlurmJobStatus] = []
    for line in text.strip().splitlines():
        if not line.strip():
            continue
        fields = line.split("|")
        if len(fields) < 4:
            continue
        job_id, job_name, state, exit_code = fields[0], fields[1], fields[2], fields[3]
        if "." in job_id:  # skip .batch / .extern sub-steps
            continue
        out.append(
            SlurmJobStatus(
                job_name=job_name,
                job_id=job_id,
                state=state.split()[0] if state else "UNKNOWN",
                exit_code=exit_code or None,
                raw=line,
            )
        )
    return out


def submit_dag(backend: "RemoteBackend", specs: list[RemoteJobSpec]) -> dict[str, str]:
    """Submit specs in dependency order; return {job_name: job_id}.

    Assumes ``depends_on`` references other job_names in *specs*. Specs are
    topologically ordered by a simple repeated-pass scheme (graphs here are tiny).
    """

    name_to_id: dict[str, str] = {}
    remaining = list(specs)
    guard = 0
    while remaining and guard < len(specs) + 2:
        guard += 1
        progressed = False
        for spec in list(remaining):
            if all(dep in name_to_id for dep in spec.depends_on):
                dep_ids = [name_to_id[d] for d in spec.depends_on]
                name_to_id[spec.job_name] = backend.submit(spec, dep_ids)
                remaining.remove(spec)
                progressed = True
        if not progressed:
            break
    for spec in remaining:  # dependency unresolved -> submit without deps, warn upstream
        logger.warning("submitting %s without unresolved deps %s", spec.job_name, spec.depends_on)
        name_to_id[spec.job_name] = backend.submit(spec, [])
    return name_to_id


def poll_until_terminal(
    backend: "RemoteBackend",
    name_to_id: dict[str, str],
    run_id: str,
    *,
    interval_s: int = 30,
    max_wait_s: int = 86400,
    on_update=None,
    sleep=time.sleep,
) -> RemoteExecutionResult:
    """Poll sacct until every job is terminal (or max_wait elapses)."""

    waited = 0
    statuses: list[SlurmJobStatus] = []
    while True:
        statuses = backend.statuses(name_to_id)
        if on_update:
            on_update(statuses)
        if all(s.is_terminal for s in statuses):
            break
        if waited >= max_wait_s:
            logger.warning("poll timed out after %ds; some jobs not terminal", waited)
            break
        sleep(interval_s)
        waited += interval_s

    failed = [s.job_name for s in statuses if not s.ok]
    return RemoteExecutionResult(
        run_id=run_id, jobs=statuses, all_ok=(len(failed) == 0), failed=failed
    )
