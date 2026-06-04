"""Parse a FastQC ``fastqc_data.txt`` into QC metrics."""

from __future__ import annotations

from typing import Any

from .base import make_result, read_lines


def parse_fastqc(path: str, sample_id: str | None = None) -> dict[str, Any]:
    """Return {result, summary} where summary has total_reads, mean_quality, etc."""

    try:
        lines = read_lines(path)
        total_reads = 0
        read_len = 0
        in_pbq = False
        q_means: list[float] = []
        for line in lines:
            if line.startswith("Total Sequences"):
                total_reads = int(line.split("\t")[1])
            elif line.startswith("Sequence length"):
                read_len = int(str(line.split("\t")[1]).split("-")[-1])
            elif line.startswith(">>Per base sequence quality"):
                in_pbq = True
            elif in_pbq and line.startswith(">>END_MODULE"):
                in_pbq = False
            elif in_pbq and not line.startswith("#"):
                parts = line.split("\t")
                if len(parts) >= 2:
                    try:
                        q_means.append(float(parts[1]))
                    except ValueError:
                        pass
        mean_q = round(sum(q_means) / len(q_means), 1) if q_means else 0.0
        summary = {
            "sample_id": sample_id,
            "total_reads": total_reads,
            "mean_quality": mean_q,
            "mean_read_length": read_len,
        }
        return {
            "result": make_result("fastqc", sample_id, parsed_table_path=path, n_records=1),
            "summary": summary,
        }
    except Exception as exc:  # never raise
        return {
            "result": make_result("fastqc", sample_id, ok=False, warnings=[f"fastqc parse failed: {exc}"]),
            "summary": {},
        }
