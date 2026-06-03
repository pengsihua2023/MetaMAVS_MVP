"""human_review_node: human-in-the-loop checkpoint.

In Phase 1 this auto-approves when running non-interactively or in dry-run mode
(simulated approval), but it is structured so a real interactive CLI prompt --
or a LangGraph ``interrupt`` -- can be slotted in later without changing the
graph wiring.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from ..state import MetaMAVSState
from ..utils.file_utils import write_json
from ..utils.logging_utils import get_logger

logger = get_logger("agents.human_review")


def _build_review_context(state: MetaMAVSState) -> dict[str, Any]:
    risk = state.get("risk_summary", {}) or {}
    novel = state.get("novel_candidate_summary", {}) or {}
    qc = state.get("qc_pass_fail", {}) or {}
    return {
        "overall_risk": risk.get("overall_risk", "Low"),
        "top_risks": risk.get("top_risks", []),
        "n_novel_candidates": int(novel.get("n_candidates", 0)),
        "qc_failures": [sid for sid, v in qc.items() if str(v).lower() == "fail"],
        "n_warnings": len(state.get("warnings", []) or []),
    }


def human_review_node(state: MetaMAVSState) -> dict[str, Any]:
    """Pause for human review; auto-approve in dry-run/non-interactive mode."""

    logger.info("Human-in-the-loop review checkpoint reached")
    run_dir = Path(state["run_dir"])
    context = _build_review_context(state)
    dry_run = state.get("dry_run", True)
    interactive = sys.stdin.isatty() and not dry_run

    triggers: list[str] = []
    if context["overall_risk"] in {"High", "Critical"}:
        triggers.append(f"overall risk = {context['overall_risk']}")
    if context["n_novel_candidates"]:
        triggers.append(f"{context['n_novel_candidates']} novel candidate(s)")
    if context["qc_failures"]:
        triggers.append(f"QC failure: {', '.join(context['qc_failures'])}")

    if interactive:  # pragma: no cover - requires a real TTY
        print("\n=== MetaMAVS HUMAN REVIEW ===")
        print(f"Triggers: {'; '.join(triggers) or 'manual'}")
        print(f"Overall risk: {context['overall_risk']}")
        answer = input("Approve results for reporting? [y/N]: ").strip().lower()
        approved = answer in {"y", "yes"}
        decision = "approved" if approved else "rejected"
        notes = f"Interactive reviewer decision: {decision}"
    else:
        approved = True
        decision = "approved_simulated"
        notes = (
            "Auto-approved in dry-run/non-interactive mode. "
            f"Triggers: {'; '.join(triggers) or 'none'}."
        )

    review_record = {"decision": decision, "approved": approved, "triggers": triggers, "context": context, "notes": notes}
    write_json(run_dir / "intermediate" / "human_review.json", review_record)

    logger.info("Human review decision: %s (approved=%s)", decision, approved)

    return {
        "review_decision": decision,
        "reviewer_notes": notes,
        "approved_for_report": approved,
        "execution_log": [f"human_review: {decision}"],
    }
