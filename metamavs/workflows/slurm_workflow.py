"""SLURM workflow backend (placeholder for Phase 2).

Phase 1 only generates a SLURM submission script from the config; it does not
submit jobs. Real orchestration (dependency chains, sbatch submission, log
parsing) is added in Phase 2.
"""

from __future__ import annotations

from pathlib import Path

from ..config import MetaMAVSConfig
from ..utils.file_utils import ensure_run_dir, write_text
from ..utils.logging_utils import get_logger

logger = get_logger("workflows.slurm")

_TEMPLATE = """#!/usr/bin/env bash
#SBATCH --job-name={run_name}
#SBATCH --cpus-per-task={threads}
#SBATCH --mem=32G
#SBATCH --time=24:00:00
#SBATCH --output={run_dir}/logs/slurm_%j.out

set -euo pipefail

# Phase 1 placeholder: run the MetaMAVS workflow on a compute node.
# In Phase 2 each analysis step becomes its own dependent SLURM job.
metamavs run --config {config_path} {dry_run_flag}
"""


def generate_slurm_script(config: MetaMAVSConfig, config_path: str, dry_run: bool = True) -> Path:
    """Write a SLURM submission script and return its path."""

    run_dir = ensure_run_dir(config.project.output_dir)
    script = _TEMPLATE.format(
        run_name=config.project.run_name,
        threads=config.execution.threads,
        run_dir=run_dir,
        config_path=config_path,
        dry_run_flag="--dry-run" if dry_run else "",
    )
    path = run_dir / "commands" / "submit_slurm.sh"
    write_text(path, script)
    logger.info("SLURM script written: %s", path)
    return path
