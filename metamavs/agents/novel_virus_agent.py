"""novel_virus_screening_agent_node: assembly + novel/divergent virus screening."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from ..llm import generate_json, llm_available, resolve_params
from ..llm.prompts import NOVEL_SYSTEM, build_novel_user
from ..llm.reference import SHARED_REFERENCE
from ..state import MetaMAVSState
from ..utils.execution import make_runner, maybe_execute_step
from ..utils.file_utils import read_csv_safe, write_commands, write_csv, write_json
from ..utils.logging_utils import get_logger

logger = get_logger("agents.novel_virus")


def _load_samples(state: MetaMAVSState) -> list[dict[str, Any]]:
    path = state.get("validated_manifest_path")
    if not path or not Path(path).exists():
        return []
    return pd.read_csv(path, dtype=str).fillna("").to_dict(orient="records")


def _assembly_cmds(runner, assembler, sid, reads, out_dir, threads):
    r1 = reads[0] if reads else f"{sid}_nonhost_R1.fastq.gz"
    r2 = reads[1] if len(reads) > 1 else ""
    asm_dir = out_dir / "assembly" / sid
    if assembler == "metaspades":
        args = ["metaspades.py", "-t", threads, "-o", asm_dir]
        args += (["-1", r1, "-2", r2] if r2 else ["-s", r1])
    else:  # megahit
        args = ["megahit", "-t", threads, "-o", asm_dir]
        args += (["-1", r1, "-2", r2] if r2 else ["-r", r1])
    return [runner.build(args)]


def _screen_cmds(runner, tools, sid, out_dir, threads):
    contigs = out_dir / "assembly" / sid / "final.contigs.fa"
    cmds: list[str] = []
    if "virsorter2" in tools:
        cmds.append(runner.build(["virsorter", "run", "-w", out_dir / "virsorter2" / sid,
                                  "-i", contigs, "-j", threads, "all"]))
    if "vibrant" in tools:
        cmds.append(runner.build(["VIBRANT_run.py", "-i", contigs, "-t", threads,
                                  "-folder", out_dir / "vibrant" / sid]))
    if "genomad" in tools:
        cmds.append(runner.build(["genomad", "end-to-end", contigs, out_dir / "genomad" / sid,
                                  "/path/to/genomad_db", "--threads", threads]))
    if "checkv" in tools:
        cmds.append(runner.build(["checkv", "end_to_end", contigs, out_dir / "checkv" / sid,
                                  "-t", threads]))
    if "deepvirfinder" in tools:
        cmds.append(runner.build(["dvf.py", "-i", contigs, "-o", out_dir / "dvf" / sid, "-c", threads]))
    return cmds


def novel_virus_screening_agent_node(state: MetaMAVSState) -> dict[str, Any]:
    """Generate assembly + screening commands and summarise novel candidates.

    Novel candidates in dry-run mode are derived from taxonomy rows that are
    unclassified yet not flagged purely as low-complexity noise.
    """

    logger.info("Generating assembly and novel-virus screening commands")
    config = state["config"]
    run_dir = Path(state["run_dir"])
    threads = config.get("execution", {}).get("threads", 8)
    asm_cfg = config.get("tools", {}).get("assembly", {})
    nv_cfg = config.get("tools", {}).get("novel_virus_screening", {})
    runner = make_runner(state)

    samples = _load_samples(state)
    nonhost = state.get("non_host_fastq_paths", {})
    out_dir = run_dir / "intermediate" / "novel_virus"
    assembler = asm_cfg.get("assembler", "megahit")
    screen_tools = [t.lower() for t in nv_cfg.get("tools", ["virsorter2", "checkv"])]
    # Tool names as invoked on the command line (assembler binary differs from key).
    assembler_bin = "metaspades.py" if assembler == "metaspades" else "megahit"

    assembly_commands: list[str] = []
    novel_commands: list[str] = []
    expected_outputs: list[Any] = []

    if asm_cfg.get("enabled", True):
        for s in samples:
            assembly_commands.extend(_assembly_cmds(runner, assembler, s["sample_id"], nonhost.get(s["sample_id"], []), out_dir, threads))
            expected_outputs.append(out_dir / "assembly" / s["sample_id"] / "final.contigs.fa")
    if nv_cfg.get("enabled", True):
        for s in samples:
            novel_commands.extend(_screen_cmds(runner, screen_tools, s["sample_id"], out_dir, threads))

    # Map screening-tool config keys to their actual command-line binaries.
    _SCREEN_BIN = {
        "virsorter2": "virsorter", "vibrant": "VIBRANT_run.py",
        "genomad": "genomad", "checkv": "checkv", "deepvirfinder": "dvf.py",
    }
    screen_bins = [_SCREEN_BIN.get(t, t) for t in screen_tools]
    tools_needed = ([assembler_bin] if asm_cfg.get("enabled", True) else []) + (
        screen_bins if nv_cfg.get("enabled", True) else []
    )
    exec_report, exec_warnings, _fb = maybe_execute_step(
        state=state, runner=runner, step="novel_virus", commands=assembly_commands + novel_commands,
        tools=tools_needed, expected_outputs=expected_outputs, log_dir=run_dir / "logs",
    )

    asm_path = write_commands(run_dir, "04_assembly", assembly_commands)
    nv_path = write_commands(run_dir, "05_novel_virus", novel_commands)

    # Derive candidate novel viruses from unclassified taxonomy rows.
    candidates: list[dict[str, Any]] = []
    tax_path = state.get("cleaned_taxonomy_table_path")
    if tax_path and Path(tax_path).exists():
        tax = read_csv_safe(tax_path)
        for _, r in tax.iterrows():
            unclassified = int(r.get("taxid", 0) or 0) == 0
            divergent = float(r.get("confidence", 1.0)) < 0.6
            low_complexity = "low-complexity" in str(r.get("taxon_name", "")).lower()
            if unclassified and divergent and not low_complexity:
                candidates.append(
                    {
                        "candidate_id": f"NVC_{len(candidates) + 1:03d}",
                        "putative_taxon": r["taxon_name"],
                        "family_hint": r.get("family", "unclassified"),
                        "total_reads": int(r.get("total_reads", 0) or 0),
                        "confidence": float(r.get("confidence", 0.0) or 0.0),
                        "evidence": "unclassified + divergent (low classification confidence)",
                    }
                )

    cand_path = write_csv(run_dir / "tables" / "novel_candidate_table.csv", candidates)

    # LLM agent layer (optional): interpret the novel/divergent candidates.
    llm_cfg = config.get("llm", {}) or {}
    llm_assessment = None
    if candidates and llm_cfg.get("enabled", False) and llm_available():
        data = generate_json(
            NOVEL_SYSTEM, build_novel_user(candidates), cached_prefix=SHARED_REFERENCE,
            **resolve_params(llm_cfg, "novel_virus"),
        )
        if data:
            llm_assessment = data
            logger.info("Novel screening: LLM assessed %d candidate(s)", len(candidates))

    summary = {
        "n_candidates": len(candidates),
        "assembler": assembler,
        "screening_tools": screen_tools,
        "candidates": candidates,
        "exec_mode": exec_report["mode"],
        "llm_assessment": llm_assessment,
        "mode": "llm" if llm_assessment else "deterministic",
        "note": "Candidates derived from synthetic taxonomy in dry-run mode.",
    }
    write_json(run_dir / "intermediate" / "novel_candidate_summary.json", summary)

    warnings = list(exec_warnings)
    if candidates:
        warnings.append(f"{len(candidates)} novel/divergent viral candidate(s) require expert review")

    logger.info("Novel screening: %d candidate(s), exec=%s", len(candidates), exec_report["mode"])

    return {
        "assembly_commands": assembly_commands,
        "novel_virus_commands": novel_commands,
        "novel_candidate_table_path": str(cand_path),
        "novel_candidate_summary": {"assembly_commands_path": str(asm_path),
                                    "screening_commands_path": str(nv_path), **summary},
        "execution_reports": [exec_report],
        "warnings": warnings,
        "execution_log": [f"novel_virus_agent: {len(candidates)} candidate(s), exec={exec_report['mode']}"],
    }
