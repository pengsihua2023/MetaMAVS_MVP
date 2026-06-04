"""Parse ``samtools flagstat`` output into host-removal metrics."""

from __future__ import annotations

import re
from typing import Any

from .base import make_result, read_lines


def parse_flagstat(path: str, sample_id: str | None = None) -> dict[str, Any]:
    """Host % = mapped reads; non-host = total - mapped."""

    try:
        lines = read_lines(path)
        total = 0
        mapped = 0
        for line in lines:
            if "in total" in line:
                total = int(line.split()[0])
            elif re.search(r"\bmapped\b", line) and "primary" not in line and "%" in line:
                mapped = int(line.split()[0])
        host_pct = round(mapped / total * 100, 1) if total else 0.0
        non_host = max(0, total - mapped)
        summary = {
            "sample_id": sample_id,
            "host_read_pct": host_pct,
            "non_host_reads": non_host,
            "total_reads": total,
        }
        return {
            "result": make_result("host_removal", sample_id, parsed_table_path=path, n_records=1),
            "summary": summary,
        }
    except Exception as exc:
        return {
            "result": make_result("host_removal", sample_id, ok=False, warnings=[f"flagstat parse failed: {exc}"]),
            "summary": {},
        }
