"""qc_agent_node: generate QC commands and summarise read quality."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from ..llm import generate, llm_available, resolve_params
from ..llm.prompts import QC_SYSTEM, build_qc_user
from ..llm.reference import SHARED_REFERENCE
from ..state import MetaMAVSState
from ..utils.execution import make_runner, maybe_execute_step
from ..utils.file_utils import write_commands, write_json
from ..utils.logging_utils import get_logger


def _llm_qc(state: MetaMAVSState, qc_summary: dict) -> str | None:
    """Optional LLM QC-adequacy assessment; None on disabled/no-key/failure."""

    llm_cfg = (state.get("config", {}) or {}).get("llm", {}) or {}
    if not llm_cfg.get("enabled", False) or not llm_available() or not qc_summary.get("per_sample"):
        return None
    # Don't interpret synthetic/placeholder QC (e.g. when QC isn't actually run).
    if "synthetic" in str(qc_summary.get("note", "")).lower():
        return None
    return generate(QC_SYSTEM, build_qc_user(qc_summary), cached_prefix=SHARED_REFERENCE,
                    **resolve_params(llm_cfg, "qc"))

logger = get_logger("agents.qc")

# Minimal QC thresholds applied when real metrics exist. In dry-run we emit
# synthetic-but-plausible metrics so the pass/fail logic is exercised.
MIN_MEAN_QUALITY = 25.0
MIN_READS = 100_000


def _load_samples(state: MetaMAVSState) -> list[dict[str, Any]]:
    path = state.get("validated_manifest_path")
    if not path or not Path(path).exists():
        return []
    return pd.read_csv(path, dtype=str).fillna("").to_dict(orient="records")


def qc_agent_node(state: MetaMAVSState) -> dict[str, Any]:
    """Build FastQC/fastp/MultiQC commands and produce a QC summary."""

    logger.info("Generating QC commands and summary")
    config = state["config"]
    run_dir = Path(state["run_dir"])
    threads = config.get("execution", {}).get("threads", 8)
    qc_cfg = config.get("tools", {}).get("qc", {})
    runner = make_runner(state)

    samples = _load_samples(state)
    commands: list[str] = []
    qc_pass_fail: dict[str, str] = {}
    per_sample: list[dict[str, Any]] = []
    expected_outputs: list[Any] = []
    enabled_tools = [t for t in ("fastqc", "fastp", "multiqc") if qc_cfg.get(t, True)]

    qc_dir = run_dir / "intermediate" / "qc"

    for i, s in enumerate(samples):
        sid = s["sample_id"]
        r1, r2 = s.get("read1", ""), s.get("read2", "")

        if qc_cfg.get("fastqc", True):
            commands.append(runner.build(["fastqc", "-t", threads, "-o", qc_dir / "fastqc", r1] + ([r2] if r2 else [])))
        if qc_cfg.get("fastp", True):
            out1 = qc_dir / "fastp" / f"{sid}_R1.trimmed.fastq.gz"
            args = ["fastp", "-w", threads, "-i", r1, "-o", out1]
            if r2:
                out2 = qc_dir / "fastp" / f"{sid}_R2.trimmed.fastq.gz"
                args += ["-I", r2, "-O", out2]
            fastp_json = qc_dir / "fastp" / f"{sid}.fastp.json"
            args += ["-j", fastp_json, "-h", qc_dir / "fastp" / f"{sid}.fastp.html"]
            commands.append(runner.build(args))
            expected_outputs.append(fastp_json)

        # Synthetic metrics (deterministic) for dry-run demonstration.
        # mean_q dips below the threshold for every 3rd sample to exercise the
        # QC-failure path; read counts stay positive and above the floor.
        mean_q = 36.0 - (i % 3) * 6.0  # 36, 30, 24, 36, ...
        n_reads = 1_500_000 + (i % 4) * 250_000
        passed = mean_q >= MIN_MEAN_QUALITY and n_reads >= MIN_READS
        qc_pass_fail[sid] = "pass" if passed else "fail"
        per_sample.append(
            {
                "sample_id": sid,
                "mean_quality": round(mean_q, 1),
                "total_reads": int(n_reads),
                "adapter_pct": round(2.0 + (i % 3) * 1.5, 1),
                "mean_read_length": 150,
                "qc_status": qc_pass_fail[sid],
            }
        )

    if qc_cfg.get("multiqc", True) and samples:
        commands.append(runner.build(["multiqc", qc_dir, "-o", qc_dir / "multiqc"]))

    # Phase 2: real execution (no-op in dry-run; graceful fallback if tools absent).
    exec_report, exec_warnings, _fell_back = maybe_execute_step(
        state=state, runner=runner, step="qc", commands=commands,
        tools=enabled_tools, expected_outputs=expected_outputs, log_dir=run_dir / "logs",
    )

    cmd_path = write_commands(run_dir, "01_qc", commands)
    qc_summary = {
        "n_samples": len(samples),
        "n_pass": sum(1 for v in qc_pass_fail.values() if v == "pass"),
        "n_fail": sum(1 for v in qc_pass_fail.values() if v == "fail"),
        "thresholds": {"min_mean_quality": MIN_MEAN_QUALITY, "min_reads": MIN_READS},
        "per_sample": per_sample,
        "note": "Metrics are synthetic placeholders in dry-run mode.",
    }
    llm_qc = _llm_qc(state, qc_summary)
    if llm_qc:
        qc_summary["llm_assessment"] = llm_qc
        qc_summary["mode"] = "llm"
    summary_path = write_json(run_dir / "intermediate" / "qc_summary.json", qc_summary)

    warnings = list(exec_warnings)
    if qc_summary["n_fail"]:
        warnings.append(f"{qc_summary['n_fail']} sample(s) failed QC thresholds")

    logger.info("QC: %d pass, %d fail (exec mode=%s)", qc_summary["n_pass"], qc_summary["n_fail"], exec_report["mode"])

    return {
        "qc_commands": commands,
        "qc_summary_path": str(summary_path),
        "qc_summary": {"commands_path": str(cmd_path), "exec_mode": exec_report["mode"], **qc_summary},
        "qc_pass_fail": qc_pass_fail,
        "execution_reports": [exec_report],
        "warnings": warnings,
        "execution_log": [f"qc_agent: {len(commands)} command(s), exec={exec_report['mode']}"],
    }
