"""risk_assessment_agent_node: combine evidence into transparent risk levels."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from ..llm import generate_json, llm_available
from ..llm.prompts import RISK_SYSTEM, build_risk_user
from ..pathogens import match_high_risk
from ..routing import should_request_review
from ..state import MetaMAVSState
from ..utils.file_utils import read_csv_safe, write_csv, write_json
from ..utils.logging_utils import get_logger

logger = get_logger("agents.risk")

_RISK_ORDER = {"Low": 0, "Medium": 1, "High": 2, "Critical": 3}


def _more_severe(a: str, b: str) -> str:
    return a if _RISK_ORDER.get(a, 0) >= _RISK_ORDER.get(b, 0) else b


def _clamp_llm_risk(llm_level: str, is_phage: bool, flagged: bool, is_known: bool) -> str:
    """Apply safety rails to the LLM's risk call.

    Phages / likely false positives are pinned Low (LLM may not upgrade them);
    a configured high-risk pathogen is floored at High (LLM may not downgrade it);
    otherwise the LLM's judgement stands.
    """

    level = llm_level if llm_level in _RISK_ORDER else "Low"
    if is_phage or flagged:
        return "Low"
    if is_known:
        return _more_severe("High", level)
    return level


def _llm_risk(state: MetaMAVSState, evidence: list[dict]) -> dict[str, dict]:
    """Return {taxon_name: {risk_level, reasoning}} from the LLM, or {}."""

    llm_cfg = (state.get("config", {}) or {}).get("llm", {}) or {}
    if not llm_cfg.get("enabled", False) or not llm_available() or not evidence:
        return {}
    data = generate_json(
        RISK_SYSTEM, build_risk_user(evidence),
        model=llm_cfg.get("model", "claude-opus-4-8"),
        effort=llm_cfg.get("effort", "medium"), max_tokens=int(llm_cfg.get("max_tokens", 4000)),
    )
    if not data or "assessments" not in data:
        return {}
    out: dict[str, dict] = {}
    for a in data.get("assessments", []):
        name = str(a.get("taxon_name", "")).strip()
        if name:
            out[name] = {"risk_level": str(a.get("risk_level", "")).strip(),
                         "reasoning": str(a.get("reasoning", ""))}
    return out


def _assess_taxon(name, taxid, reads, is_phage, flagged, trend, high_risk_pathogens):
    """Return (risk_level, reasons) for a single taxon.

    Deliberately conservative: weak / phage / flagged signals stay Low, and a
    known pathogen is only escalated to Critical when it is *also* sharply
    increasing -- avoiding over-claiming from metagenomic reads alone. High-risk
    matching uses taxid + name aliases so full taxonomic names are recognised.
    """

    reasons: list[str] = []
    matched = match_high_risk(name, taxid, high_risk_pathogens)
    is_known_pathogen = matched is not None

    if is_phage:
        return "Low", ["environmental_phage (not a human/animal pathogen)"]
    if flagged:
        return "Low", ["flagged_as_likely_false_positive"]

    level = "Low"
    if is_known_pathogen:
        level = "High"
        reasons.append(f"matches high-risk pathogen: {matched}")
        if reads < 50:
            reasons.append("low read count — recommend confirmatory testing")
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
        tdf = read_csv_safe(trend_path)
        trend = {r["taxon_name"]: r["trend"] for _, r in tdf.iterrows()}

    all_rows = read_csv_safe(tax_path).to_dict(orient="records") if (tax_path and Path(tax_path).exists()) else []

    # Separate normalization controls (e.g. PMMoV) — reported as context, NOT
    # ranked as threats and not sent to the risk LLM.
    controls = [
        {"taxon_name": str(r["taxon_name"]), "total_reads": int(r.get("total_reads", 0) or 0),
         "role": str(r.get("control_label", "") or "control marker")}
        for r in all_rows if bool(r.get("is_control", False))
    ]
    tax_rows = [r for r in all_rows if not bool(r.get("is_control", False))]

    # Build evidence and ask the LLM agent (optional) to assess risk.
    evidence = [
        {"taxon_name": str(r["taxon_name"]), "total_reads": int(r.get("total_reads", 0) or 0),
         "is_phage": bool(r.get("is_phage", False)),
         "false_positive": bool(r.get("false_positive_flag", False)),
         "trend": trend.get(str(r["taxon_name"]), "stable"),
         "matches_high_risk_pathogen": match_high_risk(str(r["taxon_name"]), int(r.get("taxid", 0) or 0), high_risk) is not None}
        for r in tax_rows
    ]
    llm_map = _llm_risk(state, evidence)
    mode = "llm" if llm_map else "deterministic"

    risk_rows: list[dict[str, Any]] = []
    for r in tax_rows:
        name = str(r["taxon_name"])
        is_phage = bool(r.get("is_phage", False))
        flagged = bool(r.get("false_positive_flag", False))
        matched = match_high_risk(name, int(r.get("taxid", 0) or 0), high_risk)
        level, reasons = _assess_taxon(
            name, int(r.get("taxid", 0) or 0), int(r.get("total_reads", 0) or 0),
            is_phage, flagged, trend.get(name, "stable"), high_risk,
        )
        # LLM agent layer: use its call (with safety-rail clamping) + reasoning.
        if name in llm_map:
            llm_level = llm_map[name]["risk_level"]
            clamped = _clamp_llm_risk(llm_level, is_phage, flagged, matched is not None)
            reasons = [f"[LLM] {llm_map[name]['reasoning']}".strip()]
            if clamped != llm_level:
                reasons.append(f"(adjusted from LLM '{llm_level}' to honour safety rails)")
            level = clamped
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
        "controls": controls,
        "mode": mode,
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

    logger.info("Risk (%s): overall=%s, review_required=%s", mode, overall, review_required)

    return {
        "risk_table_path": str(risk_path),
        "risk_summary": risk_summary,
        "recommended_followup_actions": actions,
        "review_required": review_required,
        "execution_log": [f"risk_assessment_agent: overall={overall}, review={review_required} (mode={mode})"],
    }
