"""viral_detection_agent_node: generate detection commands and viral hit tables.

In dry-run mode this emits a small, deterministic synthetic set of viral hits
so the rest of the pipeline (taxonomy, abundance, risk, report) has realistic
data to operate on. The synthetic catalogue deliberately includes a high-risk
pathogen, an environmental phage, a low-confidence hit and a divergent
unclassified signal so that downstream routing is exercised.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from ..state import MetaMAVSState
from ..utils.command_runner import CommandRunner
from ..utils.file_utils import write_commands, write_csv, write_json
from ..utils.logging_utils import get_logger

logger = get_logger("agents.viral_detection")

# Reference catalogue of synthetic taxa: (taxon, family, taxid, genome_kb, confidence).
_CATALOGUE = [
    ("SARS-CoV-2", "Coronaviridae", 2697049, 29.9, 0.98),
    ("Influenza A virus", "Orthomyxoviridae", 11320, 13.5, 0.95),
    ("Norovirus", "Caliciviridae", 11983, 7.6, 0.91),
    ("Escherichia phage T4", "Straboviridae", 10665, 168.9, 0.99),
    ("uncultured crAssphage", "Crassvirales", 1262072, 97.0, 0.88),
    ("unclassified divergent RNA virus", "unclassified", 0, 10.2, 0.42),
    ("low-complexity viral fragment", "unclassified", 0, 1.0, 0.20),
]


def _load_samples(state: MetaMAVSState) -> list[dict[str, Any]]:
    path = state.get("validated_manifest_path")
    if not path or not Path(path).exists():
        return []
    return pd.read_csv(path, dtype=str).fillna("").to_dict(orient="records")


def _detection_commands(runner, tools, dbs, nonhost, sid, out_dir, threads):
    cmds: list[str] = []
    reads = nonhost.get(sid, [])
    r1 = reads[0] if reads else f"{sid}_nonhost_R1.fastq.gz"
    r2 = reads[1] if len(reads) > 1 else ""
    if "kraken2" in tools:
        args = ["kraken2", "--db", dbs.get("kraken2_db") or "/path/to/kraken2/viral_db",
                "--threads", threads, "--report", out_dir / f"{sid}.kraken2.report",
                "--output", out_dir / f"{sid}.kraken2.out"]
        args += (["--paired", r1, r2] if r2 else [r1])
        cmds.append(runner.build(args))
    if "krakenuniq" in tools:
        cmds.append(runner.build(["krakenuniq", "--db", "/path/to/krakenuniq_db", "--threads", threads,
                                  "--report-file", out_dir / f"{sid}.krakenuniq.report", r1] + ([r2] if r2 else [])))
    if "centrifuge" in tools:
        cmds.append(runner.build(["centrifuge", "-x", "/path/to/centrifuge_index", "-p", threads,
                                  "-1" if r2 else "-U", r1] + (["-2", r2] if r2 else []) +
                                 ["--report-file", out_dir / f"{sid}.centrifuge.report"]))
    if "diamond" in tools:
        cmds.append(runner.build(["diamond", "blastx", "--db", dbs.get("diamond_db") or "/path/to/rvdb.dmnd",
                                  "--threads", threads, "-q", r1, "-o", out_dir / f"{sid}.diamond.tsv",
                                  "--outfmt", "6"]))
    if "blast" in tools:
        cmds.append(runner.build(["blastn", "-db", "/path/to/viral_nt", "-num_threads", threads,
                                  "-query", f"{sid}.contigs.fasta", "-out", out_dir / f"{sid}.blast.tsv",
                                  "-outfmt", "6"]))
    return cmds


def viral_detection_agent_node(state: MetaMAVSState) -> dict[str, Any]:
    """Generate viral detection commands and (dry-run) synthetic hit tables."""

    logger.info("Generating viral detection commands and candidate taxa")
    config = state["config"]
    run_dir = Path(state["run_dir"])
    threads = config.get("execution", {}).get("threads", 8)
    vd_cfg = config.get("tools", {}).get("viral_detection", {})
    tools = [t.lower() for t in vd_cfg.get("tools", ["kraken2", "diamond"])]
    dbs = {"kraken2_db": vd_cfg.get("kraken2_db"), "diamond_db": vd_cfg.get("diamond_db")}
    runner = CommandRunner(dry_run=state.get("dry_run", True), threads=threads)

    samples = _load_samples(state)
    nonhost = state.get("non_host_fastq_paths", {})
    out_dir = run_dir / "intermediate" / "viral_detection"

    commands: list[str] = []
    raw_hits: list[dict[str, Any]] = []

    for si, s in enumerate(samples):
        sid = s["sample_id"]
        commands.extend(_detection_commands(runner, tools, dbs, nonhost, sid, out_dir, threads))
        # Deterministic synthetic hits: vary read counts per sample index.
        for ti, (taxon, family, taxid, glen, conf) in enumerate(_CATALOGUE):
            base = 1500 // (ti + 1)
            reads = max(2, base + si * 120 - ti * 30)
            if (si + ti) % 5 == 0 and ti >= 5:
                reads = 4  # occasionally a very low-count hit
            raw_hits.append(
                {
                    "sample_id": sid,
                    "taxon_name": taxon,
                    "family": family,
                    "taxid": taxid,
                    "genome_length_kb": glen,
                    "reads": int(reads),
                    "confidence": conf,
                    "tool": tools[0] if tools else "kraken2",
                }
            )

    cmd_path = write_commands(run_dir, "03_viral_detection", commands)
    raw_path = write_csv(run_dir / "tables" / "raw_viral_hits.csv", raw_hits)

    # Candidate taxa: distinct taxa aggregated across samples.
    agg: dict[str, dict[str, Any]] = {}
    for h in raw_hits:
        key = h["taxon_name"]
        agg.setdefault(key, {"taxon_name": key, "family": h["family"], "taxid": h["taxid"],
                             "genome_length_kb": h["genome_length_kb"], "total_reads": 0,
                             "max_confidence": 0.0, "n_samples": 0})
        agg[key]["total_reads"] += h["reads"]
        agg[key]["max_confidence"] = max(agg[key]["max_confidence"], h["confidence"])
        agg[key]["n_samples"] += 1
    candidates = sorted(agg.values(), key=lambda d: d["total_reads"], reverse=True)
    cand_path = write_csv(run_dir / "tables" / "candidate_viral_taxa.csv", candidates)

    summary = {
        "tools": tools,
        "n_raw_hits": len(raw_hits),
        "n_candidate_taxa": len(candidates),
        "n_samples": len(samples),
        "note": "Hit tables are synthetic placeholders in dry-run mode.",
    }
    write_json(run_dir / "intermediate" / "viral_detection_summary.json", summary)

    logger.info("Viral detection: %d candidate taxa across %d sample(s)", len(candidates), len(samples))

    return {
        "viral_detection_commands": commands,
        "raw_viral_hits_path": str(raw_path),
        "candidate_viral_taxa_path": str(cand_path),
        "viral_detection_summary": {"commands_path": str(cmd_path), **summary},
        "execution_log": [f"viral_detection_agent: {len(candidates)} candidate taxa"],
    }
