"""Parse CheckV ``quality_summary.tsv`` into novel-candidate quality records."""

from __future__ import annotations

from typing import Any

from .base import make_result, read_lines


def parse_checkv(path: str, sample_id: str | None = None) -> dict[str, Any]:
    """Extract per-contig completeness/quality for novel viral candidates."""

    try:
        lines = read_lines(path)
        if not lines:
            return {"result": make_result("checkv", sample_id, n_records=0), "records": []}
        header = [h.strip() for h in lines[0].split("\t")]
        idx = {h: i for i, h in enumerate(header)}
        records: list[dict[str, Any]] = []
        for line in lines[1:]:
            f = line.split("\t")
            if len(f) < len(header):
                continue
            def g(col, default=""):
                return f[idx[col]] if col in idx and idx[col] < len(f) else default
            try:
                completeness = float(g("completeness", "0") or 0)
            except ValueError:
                completeness = 0.0
            records.append({
                "sample_id": sample_id,
                "contig_id": g("contig_id"),
                "checkv_quality": g("checkv_quality"),
                "completeness": completeness,
                "viral_genes": g("viral_genes"),
                "tool": "checkv",
            })
        return {
            "result": make_result("checkv", sample_id, parsed_table_path=path, n_records=len(records)),
            "records": records,
        }
    except Exception as exc:
        return {"result": make_result("checkv", sample_id, ok=False, warnings=[f"checkv parse failed: {exc}"]),
                "records": []}
