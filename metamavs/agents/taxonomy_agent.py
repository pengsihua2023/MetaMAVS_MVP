"""taxonomy_classification_agent_node: normalise taxonomy and flag false positives."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from ..controls import match_control
from ..llm import generate_json, llm_available
from ..llm.prompts import TAXONOMY_SYSTEM, build_taxonomy_user
from ..state import MetaMAVSState
from ..utils.file_utils import read_csv_safe, write_csv, write_json
from ..utils.logging_utils import get_logger
from ..utils.taxonomy_utils import flag_false_positive, is_phage

logger = get_logger("agents.taxonomy")


def _llm_taxonomy(state: MetaMAVSState, candidates: list[dict]) -> dict[str, dict]:
    """Return {taxon_name: {is_phage, false_positive, rationale}} from the LLM, or {}.

    Used to AUGMENT the deterministic flags (union — can only add caution).
    """

    llm_cfg = (state.get("config", {}) or {}).get("llm", {}) or {}
    if not llm_cfg.get("enabled", False) or not llm_available() or not candidates:
        return {}
    data = generate_json(
        TAXONOMY_SYSTEM, build_taxonomy_user(candidates),
        model=llm_cfg.get("model", "claude-opus-4-8"),
        effort=llm_cfg.get("effort", "medium"), max_tokens=int(llm_cfg.get("max_tokens", 4000)),
    )
    if not data or "taxa" not in data:
        return {}
    out: dict[str, dict] = {}
    for t in data.get("taxa", []):
        name = str(t.get("taxon_name", "")).strip()
        if name:
            out[name] = {"is_phage": bool(t.get("is_phage", False)),
                         "false_positive": bool(t.get("false_positive", False)),
                         "rationale": str(t.get("rationale", ""))}
    return out


def taxonomy_classification_agent_node(state: MetaMAVSState) -> dict[str, Any]:
    """Clean candidate taxa, assign ranks and flag likely false positives."""

    logger.info("Normalising taxonomy and flagging false positives")
    run_dir = Path(state["run_dir"])
    cand_path = state.get("candidate_viral_taxa_path")

    if not cand_path or not Path(cand_path).exists():
        warning = "No candidate viral taxa available for taxonomy classification"
        logger.warning(warning)
        return {
            "taxonomy_summary": {"n_taxa": 0, "n_flagged": 0},
            "warnings": [warning],
            "execution_log": ["taxonomy_agent: no candidates to classify"],
        }

    candidates = read_csv_safe(cand_path).to_dict(orient="records")
    cleaned: list[dict[str, Any]] = []
    fp_flags: list[dict[str, Any]] = []

    # LLM agent layer (optional). Augments deterministic flags within safety
    # rails: it can only ADD caution (union of flags), never remove it.
    llm_map = _llm_taxonomy(state, candidates)
    mode = "llm" if llm_map else "deterministic"

    for c in candidates:
        taxon = str(c.get("taxon_name", ""))
        taxid = int(c.get("taxid", 0) or 0)
        family = str(c.get("family", "unclassified"))
        reads = int(c.get("total_reads", 0) or 0)
        conf = float(c.get("max_confidence", 0.0) or 0.0)

        # Derive a coarse rank from available evidence.
        rank = "species" if taxid > 0 else "unclassified"
        phage = is_phage(taxon)
        control = match_control(taxon, taxid)  # PMMoV etc. -> normalization control
        flagged, reasons = flag_false_positive(
            {"taxon_name": taxon, "reads": reads, "confidence": conf}
        )

        # Merge LLM judgement (union → only adds caution) + keep its rationale.
        llm_rationale = ""
        if taxon in llm_map:
            lj = llm_map[taxon]
            if lj["is_phage"] and not phage:
                phage = True
                reasons.append("llm:phage")
            if lj["false_positive"] and not flagged:
                flagged = True
                reasons.append("llm:false_positive")
            llm_rationale = lj["rationale"]

        record = {
            "taxon_name": taxon,
            "rank": rank,
            "family": family,
            "taxid": taxid,
            "total_reads": reads,
            "confidence": conf,
            "is_phage": phage,
            "is_control": bool(control),
            "control_label": control or "",
            "false_positive_flag": flagged,
            "flag_reasons": ";".join(reasons),
            "llm_rationale": llm_rationale,
        }
        cleaned.append(record)
        if flagged:
            fp_flags.append({"taxon_name": taxon, "reasons": ";".join(reasons), "total_reads": reads})

    clean_path = write_csv(run_dir / "tables" / "cleaned_taxonomy_table.csv", cleaned)
    fp_path = write_csv(run_dir / "tables" / "false_positive_flags.csv", fp_flags)

    n_phage = sum(1 for r in cleaned if r["is_phage"])
    n_control = sum(1 for r in cleaned if r["is_control"])
    n_pathogen_like = sum(
        1 for r in cleaned if not r["is_phage"] and not r["is_control"] and not r["false_positive_flag"]
    )
    summary = {
        "n_taxa": len(cleaned),
        "n_flagged": len(fp_flags),
        "n_phage": n_phage,
        "n_control": n_control,
        "n_pathogen_like": n_pathogen_like,
        "families": sorted({r["family"] for r in cleaned}),
        "mode": mode,
    }
    write_json(run_dir / "intermediate" / "taxonomy_summary.json", summary)

    warnings = []
    if len(fp_flags):
        warnings.append(f"{len(fp_flags)} taxon(a) flagged as likely false positives / phage / low-confidence")

    logger.info("Taxonomy (%s): %d taxa, %d flagged (%d phage)", mode, len(cleaned), len(fp_flags), n_phage)

    return {
        "cleaned_taxonomy_table_path": str(clean_path),
        "false_positive_flags_path": str(fp_path),
        "taxonomy_summary": summary,
        "warnings": warnings,
        "execution_log": [f"taxonomy_agent: {len(cleaned)} taxa, {len(fp_flags)} flagged (mode={mode})"],
    }
