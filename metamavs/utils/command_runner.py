"""Command construction and (future) execution.

In Phase 1 the :class:`CommandRunner` only *builds* and *logs* commands; it
never executes anything when ``dry_run`` is True. Real subprocess execution
(Phase 2) plugs into :meth:`CommandRunner.run` without changing any caller.
"""

from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .logging_utils import get_logger

logger = get_logger("utils.command_runner")


@dataclass
class CommandResult:
    """Outcome of a (potentially simulated) command invocation."""

    command: str
    returncode: int = 0
    stdout: str = ""
    stderr: str = ""
    dry_run: bool = True


@dataclass
class CommandRunner:
    """Build and optionally execute shell commands.

    Parameters
    ----------
    dry_run:
        When True (the default) commands are recorded and logged but never run.
    threads:
        Default thread count made available to command builders.
    """

    dry_run: bool = True
    threads: int = 8
    history: list[str] = field(default_factory=list)

    def build(self, parts: list[str]) -> str:
        """Join *parts* into a single safely-quoted command string and record it."""

        cmd = " ".join(shlex.quote(str(p)) if " " in str(p) else str(p) for p in parts)
        self.history.append(cmd)
        return cmd

    def run(self, command: str, cwd: str | Path | None = None) -> CommandResult:
        """Execute *command* unless in dry-run mode.

        In dry-run mode this logs the command and returns a synthetic success
        result. In real mode it runs via :func:`subprocess.run` and captures
        output. Tool-availability checks belong here in Phase 2.
        """

        if self.dry_run:
            logger.info("[dry-run] %s", command)
            return CommandResult(command=command, dry_run=True)

        logger.info("[exec] %s", command)
        proc = subprocess.run(  # noqa: S602 - intentional, commands are constructed internally
            command,
            shell=True,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
        )
        return CommandResult(
            command=command,
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            dry_run=False,
        )
