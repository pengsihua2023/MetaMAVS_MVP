"""Tests for normalization-control handling (PMMoV etc.)."""

from __future__ import annotations

import pandas as pd

from metamavs.agents.risk_assessment_agent import risk_assessment_agent_node
from metamavs.controls import match_control


def test_match_control_pmmov_by_taxid_and_name():
    assert match_control("Pepper mild mottle virus", 12239) == "Pepper mild mottle virus (PMMoV)"
    assert match_control("some PMMoV isolate", 0) == "Pepper mild mottle virus (PMMoV)"


def test_match_control_crassphage():
    assert match_control("uncultured crAssphage", 1262072) is not None


def test_non_control_returns_none():
    assert match_control("SARS-CoV-2", 2697049) is None
    assert match_control("Norwalk virus", 11983) is None


def test_risk_excludes_controls_from_ranking(tmp_path):
    (tmp_path / "tables").mkdir()
    (tmp_path / "intermediate").mkdir()
    tax = tmp_path / "cleaned_taxonomy_table.csv"
    pd.DataFrame([
        {"taxon_name": "SARS-CoV-2", "taxid": 2697049, "total_reads": 600,
         "is_phage": False, "is_control": False, "false_positive_flag": False},
        {"taxon_name": "Pepper mild mottle virus", "taxid": 12239, "total_reads": 5000,
         "is_phage": False, "is_control": True, "control_label": "Pepper mild mottle virus (PMMoV)",
         "false_positive_flag": False},
    ]).to_csv(tax, index=False)
    state = {"run_dir": str(tmp_path), "cleaned_taxonomy_table_path": str(tax),
             "config": {"risk": {"high_risk_pathogens": ["SARS-CoV-2"]}, "llm": {"enabled": False}}}
    out = risk_assessment_agent_node(state)

    rs = out["risk_summary"]
    ranked = {r["taxon_name"] for r in rs["top_risks"]}
    # PMMoV is reported as a control, NOT ranked as a risk.
    assert "Pepper mild mottle virus" not in ranked
    assert "SARS-CoV-2" in ranked
    assert any("PMMoV" in c["taxon_name"] or "Pepper" in c["taxon_name"] for c in rs["controls"])
    # PMMoV (5000 reads) must not inflate overall risk.
    assert rs["overall_risk"] == "High"
