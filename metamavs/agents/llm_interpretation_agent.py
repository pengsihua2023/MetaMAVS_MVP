"""llm_interpretation_node: optional LLM-written surveillance narrative.

Sits between risk assessment / human review and the report writer. When the LLM
is enabled AND a key is available it produces a public-health narrative from the
structured results; otherwise it is a clean no-op and the report omits the
section. Never blocks or fails the workflow.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..llm import generate, llm_available
from ..llm.prompts import SYSTEM_PROMPT, build_user_prompt
from ..state import MetaMAVSState
from ..utils.file_utils import write_text
from ..utils.logging_utils import get_logger

logger = get_logger("agents.llm_interpretation")


def llm_interpretation_agent_node(state: MetaMAVSState) -> dict[str, Any]:
    """Generate an LLM interpretation narrative (optional, graceful fallback)."""

    cfg = state.get("config", {}) or {}
    llm_cfg = cfg.get("llm", {}) or {}

    if not llm_cfg.get("enabled", False):
        logger.info("LLM interpretation disabled (llm.enabled=false) — skipping")
        return {"llm_narrative": {"enabled": False, "status": "disabled"},
                "execution_log": ["llm_interpretation: disabled"]}

    if not llm_available():
        warn = "LLM interpretation enabled but no ANTHROPIC_API_KEY/SDK — using deterministic report only"
        logger.warning(warn)
        return {"llm_narrative": {"enabled": True, "status": "no_key"},
                "warnings": [warn], "execution_log": ["llm_interpretation: no key"]}

    logger.info("Generating LLM surveillance narrative")
    narrative = generate(
        SYSTEM_PROMPT,
        build_user_prompt(state),
        model=llm_cfg.get("model", "claude-opus-4-8"),
        effort=llm_cfg.get("effort", "medium"),
        max_tokens=int(llm_cfg.get("max_tokens", 4000)),
    )

    if not narrative:
        warn = "LLM interpretation returned no content — using deterministic report only"
        logger.warning(warn)
        return {"llm_narrative": {"enabled": True, "status": "failed"},
                "warnings": [warn], "execution_log": ["llm_interpretation: failed"]}

    run_dir = Path(state["run_dir"])
    md_path = write_text(run_dir / "intermediate" / "llm_narrative.md", narrative)
    logger.info("LLM narrative written: %s", md_path)
    return {
        "llm_narrative": {"enabled": True, "status": "ok",
                          "model": llm_cfg.get("model", "claude-opus-4-8"),
                          "text": narrative, "path": str(md_path)},
        "execution_log": ["llm_interpretation: narrative generated"],
    }
