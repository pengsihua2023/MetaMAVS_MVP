"""Phase 2 execution orchestration.

Sits between the agents and :class:`CommandRunner`. An agent builds its
commands as before, then calls :func:`maybe_execute_step`, which:

* in **dry-run** mode does nothing (the agent keeps using synthetic data);
* in **real** mode checks tool availability, and
    - if any required tool is missing -> **graceful fallback**: warns and lets
      the agent fall back to synthetic placeholder data so the pipeline still
      completes;
    - otherwise executes each command, validates exit codes (**warn & continue**
      on failure), validates expected output files, and writes an execution log.

Real output *parsing* into result tables is intentionally left to Phase 3; this
module is about the execution machinery only.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from .command_runner import CommandRunner
from .file_utils import write_text
from .logging_utils import get_logger

logger = get_logger("utils.execution")


def make_runner(state: dict[str, Any]) -> CommandRunner:
    """Build a :class:`CommandRunner` from the graph state's config."""

    cfg = state.get("config", {}) or {}
    execu = cfg.get("execution", {}) or {}
    return CommandRunner(
        dry_run=state.get("dry_run", True),
        threads=int(execu.get("threads", 8)),
        retries=int(execu.get("retries", 0)),
    )


def check_tools(tools: list[str]) -> dict[str, bool]:
    """Return a ``{tool: available}`` map using :func:`shutil.which`."""

    return {t: shutil.which(t) is not None for t in dict.fromkeys(tools)}


def maybe_execute_step(
    *,
    state: dict[str, Any],
    runner: CommandRunner,
    step: str,
    commands: list[str],
    tools: list[str] | None = None,
    expected_outputs: list[Any] | None = None,
    log_dir: str | Path | None = None,
) -> tuple[dict[str, Any], list[str], bool]:
    """Execute *commands* for *step* in real mode; no-op in dry-run.

    Returns ``(report, warnings, fell_back)`` where ``report`` is a structured
    dict suitable for the ``execution_reports`` state accumulator, ``warnings``
    is a list of human-readable warnings, and ``fell_back`` is True when the
    agent should use synthetic placeholder data (dry-run or missing tools).
    """

    tools = tools or []
    expected_outputs = expected_outputs or []
    warnings: list[str] = []
    report: dict[str, Any] = {"step": step, "n_commands": len(commands)}

    # Phase 3: in HPC mode, execution is deferred to the remote_execution stage.
    mode = (state.get("config", {}).get("execution", {}) or {}).get("mode", "local")
    if mode == "hpc":
        report.update(mode="remote_deferred", fell_back=True, tools={}, n_ok=0, n_failed=0, outputs_ok=None)
        return report, warnings, True

    if runner.dry_run:
        report.update(mode="dry_run", fell_back=True, tools={}, n_ok=0, n_failed=0, outputs_ok=None)
        return report, warnings, True

    availability = check_tools(tools)
    report["tools"] = availability
    missing = [t for t, ok in availability.items() if not ok]

    if missing:
        msg = (
            f"{step}: tool(s) not installed: {', '.join(missing)} — "
            "falling back to synthetic placeholder data"
        )
        logger.warning(msg)
        warnings.append(msg)
        report.update(mode="fell_back", fell_back=True, n_ok=0, n_failed=0, outputs_ok=None)
        return report, warnings, True

    # All tools present: execute commands (warn & continue on failure).
    n_ok = n_failed = 0
    log_lines: list[str] = []
    for cmd in commands:
        result = runner.run(cmd)
        log_lines.append(f"[exit {result.returncode}] {cmd}")
        if result.ok:
            n_ok += 1
        else:
            n_failed += 1
            tool_name = cmd.split()[0] if cmd.split() else cmd
            w = f"{step}: command failed (exit {result.returncode}): {tool_name} — continuing"
            logger.warning(w)
            warnings.append(w)
            if result.stderr:
                log_lines.append(f"    stderr: {result.stderr.strip()[:300]}")

    outputs_ok: bool | None = None
    if expected_outputs:
        missing_out = [str(p) for p in expected_outputs if not Path(p).exists()]
        outputs_ok = len(missing_out) == 0
        if missing_out:
            w = f"{step}: {len(missing_out)} expected output file(s) missing after execution"
            logger.warning(w)
            warnings.append(w)

    if log_dir is not None:
        write_text(Path(log_dir) / f"exec_{step}.log", "\n".join(log_lines) + "\n")

    report.update(mode="executed", fell_back=False, n_ok=n_ok, n_failed=n_failed, outputs_ok=outputs_ok)
    return report, warnings, False
