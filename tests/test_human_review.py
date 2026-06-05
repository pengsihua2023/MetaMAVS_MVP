"""Tests for the durable human-in-the-loop pause/resume flow."""

from __future__ import annotations

from pathlib import Path

import yaml

from metamavs.config import load_config
from metamavs.workflows.local_workflow import (
    load_pending_review,
    resume_after_review,
    run_local_workflow,
)


def _paused_run(tmp_path):
    """Run the dry-run example in pause mode -> pauses at human review (High risk)."""
    cfg = load_config("configs/example_config.yaml")
    cfg.project.output_dir = str(tmp_path / "run")
    cfg.human_review.mode = "pause"
    return run_local_workflow(cfg, config_path="configs/example_config.yaml",
                              dry_run=True, run_id="run_review"), tmp_path / "run"


def test_run_pauses_for_human_review(tmp_path):
    final, run_dir = _paused_run(tmp_path)
    assert final["awaiting_review"] is True
    assert final["review_decision"] == "awaiting_human_review"
    # Paused: NO report yet, and a resumable snapshot + request were written.
    assert not final.get("markdown_report_path")
    assert (run_dir / "paused_state.json").exists()
    assert (run_dir / "review_request.json").exists()
    assert load_pending_review(run_dir) is not None


def test_resume_approve_finishes_report(tmp_path):
    _final, run_dir = _paused_run(tmp_path)
    out = resume_after_review(run_dir, approved=True, notes="LGTM")
    assert out["approved_for_report"] is True
    assert out["review_decision"] == "approved"
    assert out["reviewer_notes"] == "LGTM"
    assert Path(out["markdown_report_path"]).exists()      # report now produced
    assert not (run_dir / "paused_state.json").exists()    # pause marker cleared


def test_resume_reject_produces_no_report(tmp_path):
    _final, run_dir = _paused_run(tmp_path)
    out = resume_after_review(run_dir, approved=False, notes="needs rework")
    assert out["review_decision"] == "rejected"
    assert out["workflow_status"] == "rejected_by_reviewer"
    assert not out.get("markdown_report_path")
    assert not (run_dir / "paused_state.json").exists()


def test_resume_without_pending_raises(tmp_path):
    (tmp_path / "empty").mkdir()
    try:
        resume_after_review(tmp_path / "empty", approved=True)
        assert False, "expected FileNotFoundError"
    except FileNotFoundError:
        pass


def test_auto_mode_still_auto_approves(tmp_path):
    cfg = load_config("configs/example_config.yaml")
    cfg.project.output_dir = str(tmp_path / "run")
    # default human_review.mode == "auto"
    final = run_local_workflow(cfg, config_path="x", dry_run=True, run_id="run_auto")
    assert final["awaiting_review"] is False
    assert final["review_decision"] == "approved_simulated"
    assert Path(final["markdown_report_path"]).exists()
