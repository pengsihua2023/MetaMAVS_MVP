"""taxonomy_classification_agent_node: normalise taxonomy and flag false positives."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from ..state import MetaMAVSState
from ..utils.file_utils import write_csv, write_json
from ..utils.logging_utils import get_logger
from ..utils.taxonomy_utils import flag_false_positive, is_phage

logger = get_logger("agents.taxonomy")


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

    candidates = pd.read_csv(cand_path).to_dict(orient="records")
    cleaned: list[dict[str, Any]] = []
    fp_flags: list[dict[str, Any]] = []

    for c in candidates:
        taxon = str(c.get("taxon_name", ""))
        taxid = int(c.get("taxid", 0) or 0)
        family = str(c.get("family", "unclassified"))
        reads = int(c.get("total_reads", 0) or 0)
        conf = float(c.get("max_confidence", 0.0) or 0.0)

        # Derive a coarse rank from available evidence.
        rank = "species" if taxid > 0 else "unclassified"
        phage = is_phage(taxon)
        flagged, reasons = flag_false_positive(
            {"taxon_name": taxon, "reads": reads, "confidence": conf}
        )

        record = {
            "taxon_name": taxon,
            "rank": rank,
            "family": family,
            "taxid": taxid,
            "total_reads": reads,
            "confidence": conf,
            "is_phage": phage,
            "false_positive_flag": flagged,
            "flag_reasons": ";".join(reasons),
        }
        cleaned.append(record)
        if flagged:
            fp_flags.append({"taxon_name": taxon, "reasons": ";".join(reasons), "total_reads": reads})

    clean_path = write_csv(run_dir / "tables" / "cleaned_taxonomy_table.csv", cleaned)
    fp_path = write_csv(run_dir / "tables" / "false_positive_flags.csv", fp_flags)

    n_phage = sum(1 for r in cleaned if r["is_phage"])
    n_pathogen_like = sum(1 for r in cleaned if not r["is_phage"] and not r["false_positive_flag"])
    summary = {
        "n_taxa": len(cleaned),
        "n_flagged": len(fp_flags),
        "n_phage": n_phage,
        "n_pathogen_like": n_pathogen_like,
        "families": sorted({r["family"] for r in cleaned}),
    }
    write_json(run_dir / "intermediate" / "taxonomy_summary.json", summary)

    warnings = []
    if len(fp_flags):
        warnings.append(f"{len(fp_flags)} taxon(a) flagged as likely false positives / phage / low-confidence")

    logger.info("Taxonomy: %d taxa, %d flagged (%d phage)", len(cleaned), len(fp_flags), n_phage)

    return {
        "cleaned_taxonomy_table_path": str(clean_path),
        "false_positive_flags_path": str(fp_path),
        "taxonomy_summary": summary,
        "warnings": warnings,
        "execution_log": [f"taxonomy_agent: {len(cleaned)} taxa, {len(fp_flags)} flagged"],
    }
