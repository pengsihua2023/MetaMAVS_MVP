"""Tests for the Phase 4 optional LLM interpretation layer."""

from __future__ import annotations

import metamavs.agents.llm_interpretation_agent as llm_agent
from metamavs.agents.llm_interpretation_agent import llm_interpretation_agent_node
from metamavs.llm.prompts import SYSTEM_PROMPT, build_user_prompt


def _state(tmp_path, enabled, **extra):
    s = {
        "config": {"project": {"run_name": "t"}, "llm": {"enabled": enabled}},
        "run_dir": str(tmp_path),
        "risk_summary": {"overall_risk": "High", "counts": {"High": 1},
                         "top_risks": [{"taxon_name": "Norwalk virus", "risk_level": "High",
                                        "total_reads": 26, "trend": "stable", "reasons": "Norovirus"}]},
        "taxonomy_summary": {"n_taxa": 20, "n_phage": 3, "n_flagged": 2},
        "sample_summary": {"n_samples": 1, "locations": ["sapelo2"]},
        "viral_detection_summary": {"tools": ["gottcha2"]},
        "recommended_followup_actions": ["Confirm Norwalk virus with RT-qPCR"],
    }
    s.update(extra)
    return s


def test_disabled_is_noop(tmp_path):
    out = llm_interpretation_agent_node(_state(tmp_path, enabled=False))
    assert out["llm_narrative"]["status"] == "disabled"


def test_enabled_without_key_degrades(tmp_path, monkeypatch):
    monkeypatch.setattr(llm_agent, "llm_available", lambda: False)
    out = llm_interpretation_agent_node(_state(tmp_path, enabled=True))
    assert out["llm_narrative"]["status"] == "no_key"
    assert any("no ANTHROPIC_API_KEY" in w for w in out.get("warnings", []))


def test_enabled_with_mocked_llm(tmp_path, monkeypatch):
    monkeypatch.setattr(llm_agent, "llm_available", lambda: True)
    monkeypatch.setattr(llm_agent, "generate", lambda *a, **k: "## Executive Summary\nMocked narrative.")
    out = llm_interpretation_agent_node(_state(tmp_path, enabled=True))
    assert out["llm_narrative"]["status"] == "ok"
    assert "Mocked narrative" in out["llm_narrative"]["text"]
    assert (tmp_path / "intermediate" / "llm_narrative.md").exists()


def test_generation_failure_degrades(tmp_path, monkeypatch):
    monkeypatch.setattr(llm_agent, "llm_available", lambda: True)
    monkeypatch.setattr(llm_agent, "generate", lambda *a, **k: None)
    out = llm_interpretation_agent_node(_state(tmp_path, enabled=True))
    assert out["llm_narrative"]["status"] == "failed"


def test_system_prompt_is_static_and_cautious():
    # Stable (no timestamps) for caching; encodes the scientific-caution rules.
    assert "detected sequence signal" in SYSTEM_PROMPT.lower()
    assert "confirmatory" in SYSTEM_PROMPT.lower()
    assert "phage" in SYSTEM_PROMPT.lower()


def test_user_prompt_includes_run_data(tmp_path):
    prompt = build_user_prompt(_state(tmp_path, enabled=True))
    assert "Norwalk virus" in prompt
    assert "gottcha2" in prompt
    assert "overall_risk" in prompt
