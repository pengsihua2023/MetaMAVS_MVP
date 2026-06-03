"""report_writer_agent_node: assemble Markdown and HTML surveillance reports."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .. import __version__
from ..state import MetaMAVSState
from ..utils.file_utils import utc_timestamp, write_text
from ..utils.logging_utils import get_logger
from ..utils.report_utils import md_section, md_table, render_html

logger = get_logger("agents.report_writer")


def _kv_list(pairs: list[tuple[str, Any]]) -> str:
    return "\n".join(f"- **{k}:** {v}" for k, v in pairs) + "\n"


def _build_markdown(state: MetaMAVSState) -> str:
    config = state.get("config", {})
    project = config.get("project", {})
    parts: list[str] = []

    parts.append(md_section(f"MetaMAVS Surveillance Report: {project.get('run_name', 'run')}", 1))
    parts.append(
        "> _Research-grade metagenomic virus surveillance. Signals below are "
        "**detected sequence signals**, not confirmed infections. Confirmatory "
        "testing is required before any public-health action._\n"
    )

    # Project summary
    parts.append(md_section("1. Project Summary"))
    parts.append(
        _kv_list(
            [
                ("Project", project.get("name", "MetaMAVS")),
                ("Run name", project.get("run_name", "")),
                ("Run id", state.get("run_id", "")),
                ("Mode", "dry-run" if state.get("dry_run") else "execution"),
                ("Overall risk", state.get("risk_summary", {}).get("overall_risk", "Low")),
            ]
        )
    )

    # Sample summary
    ssum = state.get("sample_summary", {})
    parts.append(md_section("2. Sample Summary"))
    parts.append(
        _kv_list(
            [
                ("Number of samples", ssum.get("n_samples", 0)),
                ("Sequencing type", ssum.get("sequencing_type", "")),
                ("Locations", ", ".join(ssum.get("locations", [])) or "n/a"),
                ("Collection dates", ", ".join(ssum.get("collection_dates", [])) or "n/a"),
            ]
        )
    )

    # QC summary
    qc = state.get("qc_summary", {})
    parts.append(md_section("3. Quality Control"))
    parts.append(_kv_list([("Passed", qc.get("n_pass", 0)), ("Failed", qc.get("n_fail", 0))]))
    if qc.get("per_sample"):
        parts.append(
            md_table(
                ["Sample", "Mean Q", "Total reads", "Adapter %", "QC"],
                [[r["sample_id"], r["mean_quality"], r["total_reads"], r["adapter_pct"], r["qc_status"]]
                 for r in qc["per_sample"]],
            )
        )

    # Host removal
    hr = state.get("host_removal_summary", {})
    parts.append(md_section("4. Host Read Removal"))
    parts.append(_kv_list([("Tool", hr.get("tool", "")), ("Host reference", hr.get("host_reference", ""))]))
    if hr.get("per_sample"):
        parts.append(
            md_table(
                ["Sample", "Host read %", "Non-host reads"],
                [[r["sample_id"], r["host_read_pct"], r["non_host_reads"]] for r in hr["per_sample"]],
            )
        )

    # Viral detection + taxonomy
    vd = state.get("viral_detection_summary", {})
    tax = state.get("taxonomy_summary", {})
    parts.append(md_section("5. Viral Detection & Taxonomy"))
    parts.append(
        _kv_list(
            [
                ("Detection tools", ", ".join(vd.get("tools", []))),
                ("Candidate taxa", vd.get("n_candidate_taxa", 0)),
                ("Flagged (phage/FP/low-conf)", tax.get("n_flagged", 0)),
                ("Phage taxa", tax.get("n_phage", 0)),
                ("Pathogen-like taxa", tax.get("n_pathogen_like", 0)),
            ]
        )
    )

    # Abundance trends
    trend = state.get("trend_summary", {})
    parts.append(md_section("6. Abundance Trends"))
    if trend.get("top_by_mean_rpm"):
        parts.append(
            md_table(
                ["Taxon", "Mean RPM", "First RPM", "Last RPM", "% change", "Trend"],
                [[t["taxon_name"], t["mean_rpm"], t["first_rpm"], t["last_rpm"], t["pct_change"], t["trend"]]
                 for t in trend["top_by_mean_rpm"]],
            )
        )
    if trend.get("sharp_increase"):
        parts.append(f"\n**Sharp increases:** {', '.join(trend['sharp_increase'])}\n")

    # Novel candidates
    novel = state.get("novel_candidate_summary", {})
    parts.append(md_section("7. Novel / Divergent Virus Candidates"))
    if novel.get("candidates"):
        parts.append(
            md_table(
                ["Candidate", "Putative taxon", "Reads", "Confidence", "Evidence"],
                [[c["candidate_id"], c["putative_taxon"], c["total_reads"], c["confidence"], c["evidence"]]
                 for c in novel["candidates"]],
            )
        )
    else:
        parts.append("_No novel candidates above threshold._\n")

    # Risk assessment
    risk = state.get("risk_summary", {})
    parts.append(md_section("8. Epidemiological Risk Assessment"))
    parts.append(_kv_list([("Overall risk", risk.get("overall_risk", "Low"))]))
    if risk.get("top_risks"):
        parts.append(
            md_table(
                ["Taxon", "Risk", "Reads", "Trend", "Reasons"],
                [[r["taxon_name"], r["risk_level"], r["total_reads"], r["trend"], r["reasons"]]
                 for r in risk["top_risks"]],
            )
        )

    # Human review
    parts.append(md_section("9. Human Review"))
    parts.append(
        _kv_list(
            [
                ("Review required", state.get("review_required", False)),
                ("Decision", state.get("review_decision", "n/a")),
                ("Approved for report", state.get("approved_for_report", False)),
                ("Reviewer notes", state.get("reviewer_notes", "n/a")),
            ]
        )
    )

    # Follow-up
    parts.append(md_section("10. Recommended Follow-up Actions"))
    actions = state.get("recommended_followup_actions", [])
    parts.append("\n".join(f"- {a}" for a in actions) + "\n" if actions else "_None._\n")

    # Warnings
    warnings = state.get("warnings", [])
    if warnings:
        parts.append(md_section("11. Warnings"))
        parts.append("\n".join(f"- {w}" for w in warnings) + "\n")

    # Reproducibility
    parts.append(md_section("12. Reproducibility"))
    parts.append(
        _kv_list(
            [
                ("MetaMAVS version", __version__),
                ("Config", state.get("config", {}).get("_config_path", "n/a")),
                ("Run directory", state.get("run_dir", "")),
                ("Generated (UTC)", utc_timestamp()),
            ]
        )
    )

    parts.append("\n---\n_Generated by MetaMAVS. Detected signals require confirmatory testing._\n")
    return "\n".join(parts)


def report_writer_agent_node(state: MetaMAVSState) -> dict[str, Any]:
    """Render the Markdown report and (optionally) an HTML version."""

    logger.info("Writing surveillance report")
    run_dir = Path(state["run_dir"])
    formats = state.get("config", {}).get("report", {}).get("formats", ["markdown", "html"])

    markdown = _build_markdown(state)
    md_path = write_text(run_dir / "report.md", markdown)
    update: dict[str, Any] = {"markdown_report_path": str(md_path)}

    if "html" in formats:
        html = render_html(markdown, title=f"MetaMAVS — {state.get('run_id', 'report')}")
        html_path = write_text(run_dir / "report.html", html)
        update["html_report_path"] = str(html_path)

    logger.info("Report written: %s", md_path)
    update["execution_log"] = ["report_writer_agent: report.md written"]
    return update
