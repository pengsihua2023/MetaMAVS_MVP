"""Parse DIAMOND blastx tabular output (outfmt 6) into protein-level hit counts."""

from __future__ import annotations

from collections import Counter
from typing import Any

from .base import make_result, read_lines


def parse_diamond(path: str, sample_id: str | None = None) -> dict[str, Any]:
    """Aggregate outfmt-6 alignments by subject into hit-count rows.

    outfmt 6 default columns: qseqid sseqid pident length mismatch gapopen
    qstart qend sstart send evalue bitscore.
    """

    try:
        counts: Counter[str] = Counter()
        for line in read_lines(path):
            if not line.strip() or line.startswith("#"):
                continue
            f = line.split("\t")
            if len(f) < 2:
                continue
            counts[f[1]] += 1
        records = [
            {"sample_id": sample_id, "subject": subj, "n_alignments": n, "tool": "diamond"}
            for subj, n in counts.most_common()
        ]
        return {
            "result": make_result("diamond", sample_id, parsed_table_path=path, n_records=len(records)),
            "records": records,
        }
    except Exception as exc:
        return {"result": make_result("diamond", sample_id, ok=False, warnings=[f"diamond parse failed: {exc}"]),
                "records": []}
