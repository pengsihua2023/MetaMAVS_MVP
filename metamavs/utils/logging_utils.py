"""Centralised logging configuration for MetaMAVS.

Uses the standard :mod:`logging` module. If :mod:`rich` is available we attach
a ``RichHandler`` for nicer terminal output, otherwise we fall back to a plain
stream handler. A file handler can additionally be attached so each run keeps a
full log under ``<run_dir>/logs/``.
"""

from __future__ import annotations

import logging
from pathlib import Path

_CONFIGURED = False
_LOG_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(level: int = logging.INFO, log_file: Path | None = None) -> None:
    """Configure the root logger once per process.

    Parameters
    ----------
    level:
        Logging level for the console handler.
    log_file:
        Optional path to also write logs to a file (always at DEBUG level).
    """

    global _CONFIGURED
    root = logging.getLogger("metamavs")
    root.setLevel(logging.DEBUG)

    if not _CONFIGURED:
        try:  # pragma: no cover - depends on optional dependency
            from rich.logging import RichHandler

            console_handler: logging.Handler = RichHandler(
                rich_tracebacks=True, show_path=False
            )
            console_handler.setFormatter(logging.Formatter("%(message)s", _DATE_FORMAT))
        except Exception:  # pragma: no cover - fallback path
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(logging.Formatter(_LOG_FORMAT, _DATE_FORMAT))

        console_handler.setLevel(level)
        root.addHandler(console_handler)
        root.propagate = False
        _CONFIGURED = True

    if log_file is not None:
        log_file = Path(log_file)
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(_LOG_FORMAT, _DATE_FORMAT))
        root.addHandler(file_handler)


def get_logger(name: str) -> logging.Logger:
    """Return a namespaced child logger, e.g. ``get_logger("agents.qc")``."""

    return logging.getLogger(f"metamavs.{name}")
