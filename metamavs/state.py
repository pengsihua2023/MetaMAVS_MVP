"""LangGraph shared state definition for MetaMAVS.

``MetaMAVSState`` is the single data structure that flows through every node
of the workflow. Each node receives the full state and returns a *partial*
update (a plain ``dict``) which LangGraph merges back in.

Most fields use last-write-wins semantics (the default LangGraph behaviour).
The three cross-cutting accumulators -- ``warnings``, ``errors`` and
``execution_log`` -- use ``operator.add`` reducers so that every node only
needs to return the *new* items it produced; LangGraph concatenates them onto
the existing lists automatically.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class MetaMAVSState(TypedDict, total=False):
    """Shared graph state for the MetaMAVS surveillance workflow.

    ``total=False`` means every key is optional, which lets nodes return small
    partial updates without having to populate the entire structure.
    """

    # --- run + config metadata -------------------------------------------
    config: dict[str, Any]
    run_id: str
    run_dir: str
    dry_run: bool

    # --- input manager ----------------------------------------------------
    manifest_path: str
    validated_manifest_path: str | None
    sample_summary: dict[str, Any]
    input_summary: dict[str, Any]

    # --- qc agent ---------------------------------------------------------
    qc_commands: list[str]
    qc_summary_path: str | None
    qc_summary: dict[str, Any]
    qc_pass_fail: dict[str, Any]

    # --- host removal agent ----------------------------------------------
    host_removal_commands: list[str]
    host_removal_summary_path: str | None
    host_removal_summary: dict[str, Any]
    non_host_fastq_paths: dict[str, Any]

    # --- viral detection agent -------------------------------------------
    viral_detection_commands: list[str]
    raw_viral_hits_path: str | None
    candidate_viral_taxa_path: str | None
    viral_detection_summary: dict[str, Any]

    # --- taxonomy classification agent -----------------------------------
    cleaned_taxonomy_table_path: str | None
    false_positive_flags_path: str | None
    taxonomy_summary: dict[str, Any]

    # --- abundance analysis agent ----------------------------------------
    abundance_table_path: str | None
    trend_summary_path: str | None
    plot_specs_path: str | None
    trend_summary: dict[str, Any]

    # --- novel virus screening agent -------------------------------------
    assembly_commands: list[str]
    novel_virus_commands: list[str]
    novel_candidate_table_path: str | None
    novel_candidate_summary: dict[str, Any]

    # --- risk assessment agent -------------------------------------------
    risk_table_path: str | None
    risk_summary: dict[str, Any]
    recommended_followup_actions: list[str]

    # --- human review -----------------------------------------------------
    review_required: bool
    review_decision: str | None
    reviewer_notes: str | None
    approved_for_report: bool

    # --- report writer ----------------------------------------------------
    markdown_report_path: str | None
    html_report_path: str | None

    # --- phase 2: real command execution ---------------------------------
    tool_availability: dict[str, Any]
    execution_reports: Annotated[list[dict[str, Any]], operator.add]

    # --- phase 3: remote (HPC) execution ---------------------------------
    remote_job_specs: Annotated[list[dict[str, Any]], operator.add]
    remote_execution_result: dict[str, Any]
    synced_manifest: dict[str, Any]
    parse_results: Annotated[list[dict[str, Any]], operator.add]

    # --- cross-cutting accumulators (use reducers) -----------------------
    warnings: Annotated[list[str], operator.add]
    errors: Annotated[list[dict[str, Any]], operator.add]
    execution_log: Annotated[list[str], operator.add]

    # --- workflow status --------------------------------------------------
    workflow_status: str
    can_continue: bool
    error_summary: dict[str, Any]
    final_summary: dict[str, Any]


# Recognised terminal/intermediate workflow status values.
STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_COMPLETED = "completed"
STATUS_COMPLETED_WITH_WARNINGS = "completed_with_warnings"
STATUS_FAILED = "failed"


def create_initial_state(
    *,
    config: dict[str, Any],
    run_id: str,
    run_dir: str,
    manifest_path: str,
    dry_run: bool,
) -> MetaMAVSState:
    """Build a fully-initialised :class:`MetaMAVSState`.

    Accumulator lists are initialised to empty so reducer-based appends behave
    predictably, and the scalar status fields are seeded with sensible
    defaults.
    """

    return MetaMAVSState(
        config=config,
        run_id=run_id,
        run_dir=run_dir,
        dry_run=dry_run,
        manifest_path=manifest_path,
        validated_manifest_path=None,
        sample_summary={},
        input_summary={},
        qc_commands=[],
        qc_summary_path=None,
        qc_summary={},
        qc_pass_fail={},
        host_removal_commands=[],
        host_removal_summary_path=None,
        host_removal_summary={},
        non_host_fastq_paths={},
        viral_detection_commands=[],
        raw_viral_hits_path=None,
        candidate_viral_taxa_path=None,
        viral_detection_summary={},
        cleaned_taxonomy_table_path=None,
        false_positive_flags_path=None,
        taxonomy_summary={},
        abundance_table_path=None,
        trend_summary_path=None,
        plot_specs_path=None,
        trend_summary={},
        assembly_commands=[],
        novel_virus_commands=[],
        novel_candidate_table_path=None,
        novel_candidate_summary={},
        risk_table_path=None,
        risk_summary={},
        recommended_followup_actions=[],
        review_required=False,
        review_decision=None,
        reviewer_notes=None,
        approved_for_report=False,
        markdown_report_path=None,
        html_report_path=None,
        tool_availability={},
        execution_reports=[],
        remote_job_specs=[],
        remote_execution_result={},
        synced_manifest={},
        parse_results=[],
        warnings=[],
        errors=[],
        execution_log=[],
        workflow_status=STATUS_PENDING,
        can_continue=True,
        error_summary={},
        final_summary={},
    )
