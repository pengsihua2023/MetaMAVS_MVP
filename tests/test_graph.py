"""Tests for graph compilation and end-to-end dry-run execution."""

from __future__ import annotations

from pathlib import Path

from metamavs.config import load_config
from metamavs.graph import build_graph, compile_graph, describe_graph
from metamavs.workflows.local_workflow import run_local_workflow


def test_graph_builds_and_compiles():
    graph = build_graph()
    assert graph is not None
    app = compile_graph()
    assert app is not None


def test_describe_graph_lists_all_nodes():
    text = describe_graph()
    for node in (
        "input_manager",
        "qc_agent",
        "host_removal_agent",
        "viral_detection_agent",
        "taxonomy_agent",
        "abundance_agent",
        "novel_virus_agent",
        "risk_assessment_agent",
        "human_review",
        "report_writer_agent",
        "final_summary",
        "error_handler",
    ):
        assert node in text


def test_compiled_graph_has_expected_nodes():
    app = compile_graph()
    nodes = set(app.get_graph().nodes.keys())
    assert {"input_manager", "risk_assessment_agent", "human_review", "report_writer_agent"} <= nodes


def test_end_to_end_dry_run(tmp_path):
    cfg = load_config("configs/example_config.yaml")
    # Redirect output into a temp directory so the test is hermetic.
    cfg.project.output_dir = str(tmp_path / "run")

    final = run_local_workflow(cfg, config_path="configs/example_config.yaml", dry_run=True, run_id="run_pytest")

    assert final["workflow_status"] in {"completed", "completed_with_warnings"}
    # Report produced.
    assert final["markdown_report_path"] and Path(final["markdown_report_path"]).exists()
    assert final["html_report_path"] and Path(final["html_report_path"]).exists()
    # Intermediate tables produced.
    assert Path(final["risk_table_path"]).exists()
    assert Path(final["abundance_table_path"]).exists()
    # SARS-CoV-2 is a configured high-risk pathogen -> overall risk should escalate.
    assert final["risk_summary"]["overall_risk"] in {"High", "Critical"}
    # High risk should have triggered human review.
    assert final["review_required"] is True
    assert final["approved_for_report"] is True
    # state.json persisted.
    assert (tmp_path / "run" / "state.json").exists()


def test_low_risk_clean_run_skips_review(tmp_path):
    """A run with no high-risk pathogens / novel candidates / QC failures
    should route directly to the report writer (review_required False)."""

    from metamavs.routing import review_router, NODE_REPORT

    state = {
        "config": {"risk": {"review_on_high_risk": True, "review_on_novel_candidates": True, "review_on_qc_failure": True}},
        "errors": [],
        "can_continue": True,
        "review_required": False,
    }
    assert review_router(state) == NODE_REPORT
