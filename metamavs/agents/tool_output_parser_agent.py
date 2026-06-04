"""tool_output_parser_agent: parse downloaded HPC outputs into normalized tables.

Overwrites the synthetic placeholders with REAL parsed data so the existing
taxonomy/abundance/risk agents operate on actual tool results. Defensive: a
malformed file degrades that one tool, never the whole run.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..parsers import PARSERS
from ..state import MetaMAVSState
from ..utils.file_utils import write_csv, write_json
from ..utils.logging_utils import get_logger

logger = get_logger("agents.tool_output_parser")

MIN_MEAN_QUALITY = 25.0
MIN_READS = 100_000


def _sample_of(name: str) -> str:
    return name.split(".")[0]


def _match_parser(basename: str):
    for token, (tool, fn) in PARSERS.items():
        if token in basename:
            return tool, fn
    return None, None


def tool_output_parser_agent_node(state: MetaMAVSState) -> dict[str, Any]:
    """Dispatch each downloaded file to its parser and aggregate tables."""

    logger.info("Parsing HPC tool outputs into normalized tables")
    run_dir = Path(state["run_dir"])
    manifest = state.get("synced_manifest", {}) or {}
    downloaded = [d for d in manifest.get("downloaded", []) if d.get("ok")]

    parse_results: list[dict[str, Any]] = []
    qc_per_sample: dict[str, dict] = {}
    host_per_sample: dict[str, dict] = {}
    kraken_rows: list[dict] = []
    bracken_by_sample: dict[str, list[dict]] = {}
    warnings: list[str] = []

    for d in downloaded:
        local = d["local_path"]
        base = Path(local).name
        tool, fn = _match_parser(base)
        if not fn:
            continue
        sid = _sample_of(base)
        out = fn(local, sid)
        parse_results.append(out["result"].model_dump())
        if not out["result"].ok:
            warnings.extend(out["result"].warnings)
            continue
        if tool == "fastqc":
            qc_per_sample[sid] = out["summary"]
        elif tool == "host_removal":
            host_per_sample[sid] = out["summary"]
        elif tool == "kraken2":
            kraken_rows.extend(out["records"])
        elif tool == "bracken":
            bracken_by_sample.setdefault(sid, []).extend(out["records"])

    update: dict[str, Any] = {"parse_results": parse_results}

    # --- QC summary + pass/fail -----------------------------------------
    if qc_per_sample:
        per = []
        qc_pf: dict[str, str] = {}
        for sid, s in qc_per_sample.items():
            passed = s.get("mean_quality", 0) >= MIN_MEAN_QUALITY and s.get("total_reads", 0) >= MIN_READS
            qc_pf[sid] = "pass" if passed else "fail"
            per.append({**s, "qc_status": qc_pf[sid]})
        qc_summary = {"n_samples": len(per), "n_pass": sum(v == "pass" for v in qc_pf.values()),
                      "n_fail": sum(v == "fail" for v in qc_pf.values()), "per_sample": per,
                      "exec_mode": "hpc", "note": "Parsed from real FastQC output."}
        write_json(run_dir / "intermediate" / "qc_summary.json", qc_summary)
        update["qc_summary"] = qc_summary
        update["qc_pass_fail"] = qc_pf
        if qc_summary["n_fail"]:
            warnings.append(f"{qc_summary['n_fail']} sample(s) failed QC thresholds (parsed)")

    # --- host removal summary -------------------------------------------
    if host_per_sample:
        per = list(host_per_sample.values())
        hr_summary = {"n_samples": len(per), "per_sample": per, "exec_mode": "hpc",
                      "note": "Parsed from real samtools flagstat output."}
        write_json(run_dir / "intermediate" / "host_removal_summary.json", hr_summary)
        update["host_removal_summary"] = hr_summary

    # --- viral hits (prefer Bracken per sample) -------------------------
    raw_hits: list[dict] = []
    samples_with_bracken = set(bracken_by_sample)
    for row in kraken_rows:
        if row["sample_id"] not in samples_with_bracken:
            raw_hits.append(row)
    for rows in bracken_by_sample.values():
        raw_hits.extend(rows)

    if raw_hits:
        raw_path = write_csv(run_dir / "tables" / "raw_viral_hits.csv", raw_hits)
        agg: dict[str, dict] = {}
        for h in raw_hits:
            k = h["taxon_name"]
            a = agg.setdefault(k, {"taxon_name": k, "family": h["family"], "taxid": h["taxid"],
                                   "genome_length_kb": h.get("genome_length_kb", 0.0),
                                   "total_reads": 0, "max_confidence": 0.0, "n_samples": 0})
            a["total_reads"] += h["reads"]
            a["max_confidence"] = max(a["max_confidence"], h["confidence"])
            a["n_samples"] += 1
        candidates = sorted(agg.values(), key=lambda d: d["total_reads"], reverse=True)
        cand_path = write_csv(run_dir / "tables" / "candidate_viral_taxa.csv", candidates)
        update["raw_viral_hits_path"] = str(raw_path)
        update["candidate_viral_taxa_path"] = str(cand_path)
        update["viral_detection_summary"] = {"tools": ["kraken2", "bracken"], "exec_mode": "hpc",
                                             "n_raw_hits": len(raw_hits), "n_candidate_taxa": len(candidates),
                                             "note": "Parsed from real Kraken2/Bracken output."}

    n_ok = sum(1 for r in parse_results if r.get("ok"))
    logger.info("Parsed %d file(s) (%d ok); %d viral hit row(s)", len(parse_results), n_ok, len(raw_hits))

    update["warnings"] = warnings
    update["execution_log"] = [f"tool_output_parser: parsed {len(parse_results)} file(s), {len(raw_hits)} hits"]
    return update
