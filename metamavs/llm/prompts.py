"""Prompts for the LLM interpretation layer.

``SYSTEM_PROMPT`` is intentionally STATIC (no timestamps / per-run data) so it
caches cleanly across runs. All volatile, per-run content goes in the user
prompt built by :func:`build_user_prompt`.
"""

from __future__ import annotations

import json
from typing import Any

# --- stable, cacheable system prompt ----------------------------------------
SYSTEM_PROMPT = """\
You are a viral metagenomic surveillance analyst writing the interpretation \
section of an automated wastewater/environmental surveillance report (the \
MetaMAVS system). You are given structured, already-computed results — your job \
is to interpret them for a public-health audience, not to recompute them.

Hard scientific-caution rules (follow exactly):
- These are DETECTED SEQUENCE SIGNALS from metagenomic reads, never confirmed \
infections or outbreaks. Always phrase accordingly.
- Never make a clinical diagnosis and never claim an outbreak from reads alone.
- Do not overstate weak signals. Explicitly flag low read counts and low \
confidence. Treat anything below ~10 supporting reads as a weak/uncertain signal.
- Report environmental bacteriophages separately from human/animal pathogens; \
phages are not a public-health risk by themselves.
- For every High/Critical detection, recommend orthogonal confirmatory testing \
(e.g. targeted RT-qPCR or amplicon sequencing) before any action.
- Be transparent and concise. Do not invent taxa, numbers, or trends not present \
in the provided data.

Write in Markdown. Use these sections, in order, and nothing else:
## Executive Summary  (3-5 sentences)
## Risk Interpretation  (per High/Critical taxon: what it is, why flagged, caveats)
## Recommended Public-Health Actions  (bulleted, prioritised, confirmatory-first)
## Caveats & Limitations  (bulleted)
Keep the whole thing under ~450 words.\
"""


def build_user_prompt(state: dict[str, Any]) -> str:
    """Render the per-run structured results into a compact prompt."""

    cfg = state.get("config", {}) or {}
    project = cfg.get("project", {}) or {}
    risk = state.get("risk_summary", {}) or {}
    tax = state.get("taxonomy_summary", {}) or {}
    sample = state.get("sample_summary", {}) or {}
    novel = state.get("novel_candidate_summary", {}) or {}
    vd = state.get("viral_detection_summary", {}) or {}

    payload = {
        "run_name": project.get("run_name", ""),
        "samples": {
            "n": sample.get("n_samples", 0),
            "locations": sample.get("locations", []),
            "collection_dates": sample.get("collection_dates", []),
            "type": "wastewater/environmental metagenome",
        },
        "detection_tools": vd.get("tools", []),
        "overall_risk": risk.get("overall_risk", "Low"),
        "risk_level_counts": risk.get("counts", {}),
        "top_risk_taxa": risk.get("top_risks", []),  # name, risk_level, total_reads, trend, reasons
        "taxonomy": {
            "n_taxa": tax.get("n_taxa", 0),
            "n_phage": tax.get("n_phage", 0),
            "n_flagged_false_positive": tax.get("n_flagged", 0),
        },
        "novel_candidates": novel.get("n_candidates", 0),
        "recommended_actions_deterministic": state.get("recommended_followup_actions", []),
    }
    return (
        "Interpret the following MetaMAVS surveillance results. Use only this data.\n\n"
        "```json\n" + json.dumps(payload, indent=2, default=str) + "\n```"
    )
