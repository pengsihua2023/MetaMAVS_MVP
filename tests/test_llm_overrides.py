"""Per-agent LLM model overrides (llm.overrides) and resolve_params()."""

from __future__ import annotations

from metamavs.config import LLMConfig
from metamavs.llm.client import DEFAULT_MODEL, resolve_params


def test_resolve_params_falls_back_to_top_level():
    llm = {"model": "claude-opus-4-8", "effort": "medium", "max_tokens": 4000}
    p = resolve_params(llm, "risk_assessment")
    assert p == {"model": "claude-opus-4-8", "effort": "medium", "max_tokens": 4000}


def test_resolve_params_applies_per_agent_override():
    llm = {
        "model": "claude-opus-4-8",
        "effort": "medium",
        "max_tokens": 4000,
        "overrides": {
            "qc": {"model": "claude-haiku-4-5", "effort": "low"},
            "risk_assessment": {"effort": "high"},  # partial: model inherited
        },
    }
    qc = resolve_params(llm, "qc")
    assert qc["model"] == "claude-haiku-4-5"
    assert qc["effort"] == "low"
    assert qc["max_tokens"] == 4000  # inherited

    risk = resolve_params(llm, "risk_assessment")
    assert risk["model"] == "claude-opus-4-8"  # inherited
    assert risk["effort"] == "high"  # overridden

    # An agent with no override gets the top-level defaults.
    tax = resolve_params(llm, "taxonomy")
    assert tax["model"] == "claude-opus-4-8" and tax["effort"] == "medium"


def test_resolve_params_empty_config_uses_library_defaults():
    p = resolve_params({}, "qc")
    assert p == {"model": DEFAULT_MODEL, "effort": "medium", "max_tokens": 4000}
    # None is tolerated too.
    assert resolve_params(None, "taxonomy")["model"] == DEFAULT_MODEL


def test_llmconfig_parses_overrides_and_roundtrips_to_dict():
    cfg = LLMConfig.model_validate(
        {
            "enabled": True,
            "model": "claude-opus-4-8",
            "overrides": {"qc": {"model": "claude-haiku-4-5", "effort": "low"}},
        }
    )
    assert cfg.overrides["qc"].model == "claude-haiku-4-5"
    # model_dump (how config enters graph state) keeps overrides as plain dicts,
    # which resolve_params consumes.
    d = cfg.model_dump(mode="json")["overrides"]["qc"]
    assert resolve_params({"model": "claude-opus-4-8", "overrides": {"qc": d}}, "qc")["model"] == "claude-haiku-4-5"
