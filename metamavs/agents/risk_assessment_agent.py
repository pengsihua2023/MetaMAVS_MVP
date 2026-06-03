"""risk_assessment_agent_node: combine evidence into transparent risk levels."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from ..routing import should_request_review
from ..state import MetaMAVSState
from ..utils.file_utils import write_csv, write_json
from ..utils.logging_utils import get_logger

logger = get_logger("agents.risk")

_RISK_ORDER = {"Low": 0, "Medium": 1, "High": 2, "Critical": 3}


def _assess_taxon(name, reads, is_phage, flagged, trend, high_risk_pathogens):
    """Return (risk_level, reasons) for a single taxon.

    Deliberately conservative: weak / phage / flagged signals stay Low, and a
    known pathogen is only escalated to Critical when it is *also* sharply
    increasing -- avoiding over-claiming from metagenomic reads alone.
    """

    reasons: list[str] = []
    is_known_pathogen = any(p.lower() in name.lower() for p in high_risk_pathogens)

    if is_phage:
        return "Low", ["environmental_phage (not a human/animal pathogen)"]
    if flagged:
        return "Low", ["flagged_as_likely_false_positive"]

    level = "Low"
    if is_known_pathogen:
        level = "High"
        reasons.append("matches configured high-risk pathogen list")
    elif reads >= 500:
        level = "Medium"
        reasons.append("substantial read support for a non-phage virus")
    else:
        reasons.append("low/uncertain signal")

    if trend == "increasing":
        reasons.append("abundance trend increasing")
        if is_known_pathogen:
            level = "Critical"
        elif level == "Low":
            level = "Medium"

    return level, reasons


def risk_assessment_agent_node(state: MetaMAVSState) -> dict[str, Any]:
    """Assign per-taxon and overall risk levels with transparent reasoning."""

    logger.info("Assessing epidemiological risk")
    config = state["config"]
    run_dir = Path(state["run_dir"])
    high_risk = config.get("risk", {}).get("high_risk_pathogens", [])

    tax_path = state.get("cleaned_taxonomy_table_path")
    trend = {t["taxon_name"]: t["trend"] for t in state.get("trend_summary", {}).get("top_by_mean_rpm", [])}
    # Build a full trend lookup from the trend table if present.
    trend_path = state.get("trend_summary_path")
    if trend_path and Path(trend_path).exists():
        tdf = pd.read_csv(trend_path)
        trend = {r["taxon_name"]: r["trend"] for _, r in tdf.iterrows()}

    risk_rows: list[dict[str, Any]] = []
    if tax_path and Path(tax_path).exists():
        for _, r in pd.read_csv(tax_path).iterrows():
            name = str(r["taxon_name"])
            level, reasons = _assess_taxon(
                name,
                int(r.get("total_reads", 0) or 0),
                bool(r.get("is_phage", False)),
                bool(r.get("false_positive_flag", False)),
                trend.get(name, "stable"),
                high_risk,
            )
            risk_rows.append(
                {
                    "taxon_name": name,
                    "risk_level": level,
                    "total_reads": int(r.get("total_reads", 0) or 0),
                    "trend": trend.get(name, "stable"),
                    "reasons": "; ".join(reasons),
                }
            )

    novel = state.get("novel_candidate_summary", {}) or {}
    for c in novel.get("candidates", []):
        risk_rows.append(
            {
                "taxon_name": c["putative_taxon"],
                "risk_level": "Medium",
                "total_reads": c.get("total_reads", 0),
                "trend": "unknown",
                "reasons": "novel/divergent candidate; requires confirmatory characterisation",
            }
        )

    risk_rows = sorted(risk_rows, key=lambda d: _RISK_ORDER.get(d["risk_level"], 0), reverse=True)
    risk_path = write_csv(run_dir / "tables" / "risk_table.csv", risk_rows)

    overall = "Low"
    for row in risk_rows:
        if _RISK_ORDER.get(row["risk_level"], 0) > _RISK_ORDER.get(overall, 0):
            overall = row["risk_level"]

    counts = {lvl: sum(1 for r in risk_rows if r["risk_level"] == lvl) for lvl in _RISK_ORDER}
    risk_summary = {
        "overall_risk": overall,
        "counts": counts,
        "top_risks": risk_rows[:5],
        "n_novel_candidates": int(novel.get("n_candidates", 0)),
    }
    write_json(run_dir / "intermediate" / "risk_summary.json", risk_summary)

    # Recommended follow-up actions (transparent, conservative).
    actions: list[str] = []
    for row in risk_rows:
        if row["risk_level"] in {"High", "Critical"}:
            actions.append(
                f"Confirm {row['taxon_name']} ({row['risk_level']}) with targeted RT-qPCR / amplicon sequencing"
            )
    if risk_summary["n_novel_candidates"]:
        actions.append("Manually curate novel/divergent candidates; verify contigs with CheckV and phylogenetics")
    if not actions:
        actions.append("Continue routine surveillance; no high-risk confirmatory testing indicated")

    # Determine whether human review is required (writes into state for router).
    interim_state = {**state, "risk_summary": risk_summary, "novel_candidate_summary": novel}
    review_required = should_request_review(interim_state)

    logger.info("Risk: overall=%s, review_required=%s", overall, review_required)

    return {
        "risk_table_path": str(risk_path),
        "risk_summary": risk_summary,
        "recommended_followup_actions": actions,
        "review_required": review_required,
        "execution_log": [f"risk_assessment_agent: overall={overall}, review={review_required}"],
    }
