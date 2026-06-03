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
