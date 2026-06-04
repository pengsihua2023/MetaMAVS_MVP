"""Shared parser helpers."""

from __future__ import annotations

from pathlib import Path

from ..remote.types import ToolOutputParseResult


def make_result(tool: str, sample_id: str | None, **kw) -> ToolOutputParseResult:
    return ToolOutputParseResult(tool=tool, sample_id=sample_id, **kw)


def read_lines(path: str) -> list[str]:
    return Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
