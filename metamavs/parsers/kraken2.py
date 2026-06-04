"""Parse Kraken2 reports and Bracken abundance tables into viral-hit rows."""

from __future__ import annotations

from typing import Any

from .base import make_result, read_lines

# Minimal taxon -> family hints for common surveillance targets (extend freely).
_FAMILY_HINTS = {
    "sars-cov-2": "Coronaviridae",
    "severe acute respiratory syndrome coronavirus 2": "Coronaviridae",
    "influenza a": "Orthomyxoviridae",
    "influenza b": "Orthomyxoviridae",
    "norovirus": "Caliciviridae",
    "enterovirus": "Picornaviridae",
    "phage": "Bacteriophage",
    "crassphage": "Crassvirales",
}


def _family_for(name: str) -> str:
    low = name.lower()
    for key, fam in _FAMILY_HINTS.items():
        if key in low:
            return fam
    return "unclassified"


def parse_kraken2(path: str, sample_id: str | None = None) -> dict[str, Any]:
    """Species-level rows from a Kraken2 report -> raw_viral_hits schema."""

    try:
        records: list[dict[str, Any]] = []
        for line in read_lines(path):
            fields = line.rstrip("\n").split("\t")
            if len(fields) < 6:
                continue
            rank = fields[3].strip()
            if rank != "S":  # species only
                continue
            try:
                reads = int(fields[1])
                taxid = int(fields[4])
            except ValueError:
                continue
            name = fields[5].strip()
            if reads <= 0 or not name:
                continue
            records.append({
                "sample_id": sample_id, "taxon_name": name, "family": _family_for(name),
                "taxid": taxid, "genome_length_kb": 0.0, "reads": reads,
                "confidence": 0.9, "tool": "kraken2",
            })
        return {
            "result": make_result("kraken2", sample_id, parsed_table_path=path, n_records=len(records)),
            "records": records,
        }
    except Exception as exc:
        return {"result": make_result("kraken2", sample_id, ok=False, warnings=[f"kraken2 parse failed: {exc}"]),
                "records": []}


def parse_bracken(path: str, sample_id: str | None = None) -> dict[str, Any]:
    """Bracken table -> viral-hit rows using new_est_reads as abundance."""

    try:
        lines = read_lines(path)
        if not lines:
            return {"result": make_result("bracken", sample_id, n_records=0), "records": []}
        header = lines[0].split("\t")
        idx = {h.strip(): i for i, h in enumerate(header)}
        name_i = idx.get("name", 0)
        taxid_i = idx.get("taxonomy_id", 1)
        reads_i = idx.get("new_est_reads", 5)
        records: list[dict[str, Any]] = []
        for line in lines[1:]:
            f = line.split("\t")
            if len(f) <= max(name_i, taxid_i, reads_i):
                continue
            try:
                reads = int(float(f[reads_i]))
                taxid = int(f[taxid_i])
            except ValueError:
                continue
            name = f[name_i].strip()
            if reads <= 0 or not name:
                continue
            records.append({
                "sample_id": sample_id, "taxon_name": name, "family": _family_for(name),
                "taxid": taxid, "genome_length_kb": 0.0, "reads": reads,
                "confidence": 0.92, "tool": "bracken",
            })
        return {
            "result": make_result("bracken", sample_id, parsed_table_path=path, n_records=len(records)),
            "records": records,
        }
    except Exception as exc:
        return {"result": make_result("bracken", sample_id, ok=False, warnings=[f"bracken parse failed: {exc}"]),
                "records": []}
