"""MetaMAVS command-line interface (Typer).

Commands
--------
``metamavs run``      Execute the workflow (use ``--dry-run`` for the prototype).
``metamavs graph``    Describe / visualise the LangGraph workflow structure.
``metamavs validate`` Validate a config + manifest without running the workflow.
``metamavs slurm``    Generate a SLURM submission script (Phase 2 placeholder).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import typer

from . import __version__
from .config import load_config
from .graph import compile_graph, describe_graph
from .schemas import validate_manifest
from .utils.logging_utils import get_logger, setup_logging
from .workflows.local_workflow import run_local_workflow

app = typer.Typer(add_completion=False, help="MetaMAVS: Metagenomic Multi-Agent Virus Surveillance System")
logger = get_logger("cli")


def _echo(msg: str) -> None:
    typer.echo(msg)


@app.callback()
def _main(version: bool = typer.Option(False, "--version", help="Show version and exit.")):
    if version:
        _echo(f"MetaMAVS {__version__}")
        raise typer.Exit()


@app.command()
def run(
    config: Path = typer.Option(..., "--config", "-c", exists=True, help="Path to YAML config."),
    dry_run: bool = typer.Option(False, "--dry-run/--execute", help="Generate commands without executing."),
    run_id: Optional[str] = typer.Option(None, "--run-id", help="Explicit run id (default: timestamp)."),
):
    """Run the full MetaMAVS surveillance workflow."""

    setup_logging(level=logging.INFO)
    cfg = load_config(config)
    # CLI --dry-run overrides config; otherwise fall back to the config value.
    effective_dry_run = True if dry_run else cfg.execution.dry_run

    final_state = run_local_workflow(
        cfg, config_path=str(config), dry_run=effective_dry_run, run_id=run_id
    )

    summary = final_state.get("final_summary", {})
    _echo("\n" + "=" * 60)
    _echo("MetaMAVS run complete")
    _echo("=" * 60)
    _echo(f"  Status        : {summary.get('status')}")
    _echo(f"  Overall risk  : {summary.get('overall_risk')}")
    high = summary.get("high_risk_detections") or []
    _echo(f"  High-risk     : {', '.join(high) if high else 'none'}")
    _echo(f"  Warnings      : {summary.get('n_warnings')}   Errors: {summary.get('n_errors')}")
    _echo(f"  Markdown      : {summary.get('markdown_report')}")
    _echo(f"  HTML          : {summary.get('html_report')}")
    _echo(f"  Run directory : {summary.get('run_dir')}")
    _echo("=" * 60)


@app.command()
def graph(
    config: Optional[Path] = typer.Option(None, "--config", "-c", help="Optional config (compiles the graph)."),
    mermaid: bool = typer.Option(False, "--mermaid", help="Also emit Mermaid diagram source."),
):
    """Describe (and optionally visualise) the LangGraph workflow."""

    setup_logging(level=logging.WARNING)
    _echo(describe_graph())

    # Compiling proves the graph is well-formed; config is optional here.
    if config is not None:
        load_config(config)
    app_graph = compile_graph()
    _echo("\nGraph compiled successfully.")

    if mermaid:
        try:
            diagram = app_graph.get_graph().draw_mermaid()
            _echo("\n--- Mermaid ---\n" + diagram)
        except Exception as exc:  # pragma: no cover - optional rendering
            _echo(f"(Mermaid rendering unavailable: {exc})")


@app.command()
def validate(
    config: Path = typer.Option(..., "--config", "-c", exists=True, help="Path to YAML config."),
):
    """Validate the config and manifest without running the workflow."""

    setup_logging(level=logging.INFO)
    cfg = load_config(config)
    _echo(f"Config OK: {config}")

    result = validate_manifest(
        cfg.input.manifest,
        sequencing_type=cfg.input.sequencing_type,
        dry_run=cfg.execution.dry_run,
        remote_data=cfg.input.remote_data,
    )
    _echo(f"Manifest : {cfg.input.manifest}")
    _echo(f"  samples : {result.summary.get('n_samples', 0)}")
    for w in result.warnings:
        _echo(f"  [warn] {w}")
    if result.is_valid:
        _echo("Manifest OK.")
    else:
        for e in result.errors:
            _echo(f"  [error] {e}")
        raise typer.Exit(code=1)


@app.command()
def tools(
    config: Path = typer.Option(..., "--config", "-c", exists=True, help="Path to YAML config."),
):
    """Check availability of the bioinformatics tools referenced by the config."""

    from .utils.command_runner import CommandRunner

    setup_logging(level=logging.WARNING)
    cfg = load_config(config)

    needed: list[str] = []
    qc = cfg.tools.qc
    needed += [t for t, on in (("fastqc", qc.fastqc), ("fastp", qc.fastp), ("multiqc", qc.multiqc)) if on]
    needed.append(cfg.tools.host_removal.tool)
    if cfg.tools.host_removal.tool in {"bwa", "minimap2"}:
        needed.append("samtools")
    needed += [t.lower() for t in cfg.tools.viral_detection.tools]
    if cfg.tools.assembly.enabled:
        needed.append("metaspades.py" if cfg.tools.assembly.assembler == "metaspades" else "megahit")
    if cfg.tools.novel_virus_screening.enabled:
        screen_bin = {"virsorter2": "virsorter", "vibrant": "VIBRANT_run.py", "genomad": "genomad",
                      "checkv": "checkv", "deepvirfinder": "dvf.py"}
        needed += [screen_bin.get(t.lower(), t.lower()) for t in cfg.tools.novel_virus_screening.tools]

    seen = list(dict.fromkeys(needed))
    _echo(f"Tool availability ({len(seen)} referenced by {config}):")
    n_ok = 0
    for tool in seen:
        ok = CommandRunner.tool_available(tool)
        n_ok += int(ok)
        _echo(f"  [{'OK ' if ok else 'MISSING'}] {tool}")
    _echo(f"\n{n_ok}/{len(seen)} available. Missing tools trigger graceful fallback in --execute mode.")


@app.command()
def review(
    run_dir: Path = typer.Option(..., "--run-dir", "-r", exists=True, help="Paused run directory."),
    approve: Optional[bool] = typer.Option(None, "--approve/--reject", help="Decision (omit to be prompted)."),
    notes: str = typer.Option("", "--notes", help="Reviewer notes."),
):
    """Human-in-the-loop: approve/reject a paused run and resume it."""

    from .workflows.local_workflow import load_pending_review, resume_after_review

    setup_logging(level=logging.INFO)
    pending = load_pending_review(run_dir)
    if pending is None:
        _echo(f"No run awaiting review in {run_dir}. (Run with human_review.mode=pause to enable.)")
        raise typer.Exit(code=1)

    ctx = (pending.get("risk_summary", {}) or {})
    _echo("\n=== MetaMAVS HUMAN REVIEW ===")
    _echo(f"  Run id       : {pending.get('run_id')}")
    _echo(f"  Overall risk : {ctx.get('overall_risk')}")
    qc = pending.get("qc_pass_fail", {}) or {}
    fails = [s for s, v in qc.items() if str(v).lower() == "fail"]
    _echo(f"  Triggers     : risk={ctx.get('overall_risk')}"
          f"{', novel candidates' if pending.get('novel_candidate_summary', {}).get('n_candidates') else ''}"
          f"{', QC fail: ' + ','.join(fails) if fails else ''}")
    _echo("  Top detections:")
    for r in ctx.get("top_risks", [])[:5]:
        _echo(f"    - {r.get('taxon_name')}: {r.get('risk_level')} ({r.get('total_reads')} reads) — {str(r.get('reasons',''))[:80]}")

    if approve is None:
        answer = typer.prompt("\nApprove results for reporting? [y/N]", default="n")
        approve = answer.strip().lower() in {"y", "yes"}

    final = resume_after_review(run_dir, approved=bool(approve), notes=notes)
    if approve:
        _echo(f"\nApproved. Report: {final.get('markdown_report_path')}")
    else:
        _echo("\nRejected — no report generated. Status: rejected_by_reviewer")


@app.command(name="remote-check")
def remote_check(
    config: Path = typer.Option(..., "--config", "-c", exists=True, help="Path to YAML config."),
):
    """Diagnose HPC readiness over SSH (connectivity, scheduler, paths, conda env).

    The first connection triggers interactive auth (e.g. GACRC Duo); with SSH
    ControlMaster enabled it is reused for the rest of the run.
    """

    from .remote.backends import SSHBackend, build_ssh_backend_opts

    setup_logging(level=logging.INFO)
    cfg = load_config(config)
    hpc = cfg.hpc
    if hpc.backend != "ssh":
        _echo(f"hpc.backend is '{hpc.backend}'; remote-check only applies to ssh.")
        raise typer.Exit(code=1)
    if not hpc.host:
        _echo("hpc.host is not set.")
        raise typer.Exit(code=1)

    backend = SSHBackend(host=hpc.host, user=hpc.user,
                         ssh_opts=build_ssh_backend_opts(hpc.model_dump()), retries=hpc.retries)
    _echo(f"Checking {hpc.user or ''}@{hpc.host} (first connect may prompt for Duo/2FA)…")
    checks = backend.connectivity_check(hpc.remote_base, hpc.conda_env)

    all_ok = True
    for name, (ok, detail) in checks.items():
        all_ok = all_ok and ok
        _echo(f"  [{'OK ' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail else ""))
    if all_ok:
        _echo("\nHPC looks ready. You can run:  metamavs run --config <cfg> --execute")
    else:
        _echo("\nSome checks failed — fix the above before an --execute run.")
        raise typer.Exit(code=1)


@app.command()
def slurm(
    config: Path = typer.Option(..., "--config", "-c", exists=True, help="Path to YAML config."),
    dry_run: bool = typer.Option(True, "--dry-run/--execute", help="Embed --dry-run in the script."),
):
    """Generate a SLURM submission script (Phase 2 placeholder)."""

    from .workflows.slurm_workflow import generate_slurm_script

    setup_logging(level=logging.INFO)
    cfg = load_config(config)
    path = generate_slurm_script(cfg, str(config), dry_run=dry_run)
    _echo(f"SLURM script written: {path}")


if __name__ == "__main__":  # pragma: no cover
    app()
