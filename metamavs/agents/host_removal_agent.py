"""host_removal_agent_node: generate host-read removal commands."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from ..state import MetaMAVSState
from ..utils.command_runner import CommandRunner
from ..utils.file_utils import write_commands, write_json
from ..utils.logging_utils import get_logger

logger = get_logger("agents.host_removal")


def _load_samples(state: MetaMAVSState) -> list[dict[str, Any]]:
    path = state.get("validated_manifest_path")
    if not path or not Path(path).exists():
        return []
    return pd.read_csv(path, dtype=str).fillna("").to_dict(orient="records")


def _bowtie2_cmds(runner, sid, r1, r2, ref, out_dir, threads):
    sam = out_dir / f"{sid}.host.sam"
    unconc = out_dir / f"{sid}_nonhost_R%.fastq.gz"
    args = ["bowtie2", "-p", threads, "-x", ref, "--very-sensitive"]
    if r2:
        args += ["-1", r1, "-2", r2, "--un-conc-gz", unconc]
    else:
        args += ["-U", r1, "--un-gz", out_dir / f"{sid}_nonhost.fastq.gz"]
    args += ["-S", sam]
    return [runner.build(args)]


def _bwa_cmds(runner, sid, r1, r2, ref, out_dir, threads):
    bam = out_dir / f"{sid}.host.bam"
    reads = [r1] + ([r2] if r2 else [])
    return [runner.build(["bwa", "mem", "-t", threads, ref] + reads + ["|", "samtools", "view", "-bS", "-f", "4", "-", ">", bam])]


def _minimap2_cmds(runner, sid, r1, r2, ref, out_dir, threads):
    bam = out_dir / f"{sid}.host.bam"
    reads = [r1] + ([r2] if r2 else [])
    return [runner.build(["minimap2", "-ax", "sr", "-t", threads, ref] + reads + ["|", "samtools", "view", "-bS", "-f", "4", "-", ">", bam])]


_BUILDERS = {"bowtie2": _bowtie2_cmds, "bwa": _bwa_cmds, "minimap2": _minimap2_cmds}


def host_removal_agent_node(state: MetaMAVSState) -> dict[str, Any]:
    """Generate host-removal commands and track non-host FASTQ outputs."""

    logger.info("Generating host-removal commands")
    config = state["config"]
    run_dir = Path(state["run_dir"])
    threads = config.get("execution", {}).get("threads", 8)
    hr_cfg = config.get("tools", {}).get("host_removal", {})
    tool = hr_cfg.get("tool", "bowtie2")
    ref = hr_cfg.get("host_reference") or "/path/to/host/reference"
    runner = CommandRunner(dry_run=state.get("dry_run", True), threads=threads)
    builder = _BUILDERS.get(tool, _bowtie2_cmds)

    samples = _load_samples(state)
    out_dir = run_dir / "intermediate" / "host_removed"
    commands: list[str] = []
    non_host_paths: dict[str, Any] = {}
    per_sample: list[dict[str, Any]] = []
    warnings: list[str] = []

    if not hr_cfg.get("host_reference"):
        warnings.append("No host_reference configured; using placeholder path in generated commands")

    for i, s in enumerate(samples):
        sid = s["sample_id"]
        r1, r2 = s.get("read1", ""), s.get("read2", "")
        commands.extend(builder(runner, sid, r1, r2, ref, out_dir, threads))

        if r2:
            paths = [str(out_dir / f"{sid}_nonhost_R1.fastq.gz"), str(out_dir / f"{sid}_nonhost_R2.fastq.gz")]
        else:
            paths = [str(out_dir / f"{sid}_nonhost.fastq.gz")]
        non_host_paths[sid] = paths

        host_pct = 85.0 - (i % 5) * 7.0  # synthetic host fraction
        per_sample.append(
            {
                "sample_id": sid,
                "host_read_pct": round(host_pct, 1),
                "non_host_reads": int(2_000_000 * (1 - host_pct / 100)),
                "tool": tool,
            }
        )

    cmd_path = write_commands(run_dir, "02_host_removal", commands)
    summary = {
        "tool": tool,
        "host_reference": ref,
        "n_samples": len(samples),
        "per_sample": per_sample,
        "note": "Host fractions are synthetic placeholders in dry-run mode.",
    }
    summary_path = write_json(run_dir / "intermediate" / "host_removal_summary.json", summary)

    logger.info("Host removal: %d command(s) for %d sample(s)", len(commands), len(samples))

    return {
        "host_removal_commands": commands,
        "host_removal_summary_path": str(summary_path),
        "host_removal_summary": {"commands_path": str(cmd_path), **summary},
        "non_host_fastq_paths": non_host_paths,
        "warnings": warnings,
        "execution_log": [f"host_removal_agent: generated {len(commands)} command(s) ({tool})"],
    }
