"""Manifest schema and validation logic.

The sample manifest is the primary user-supplied input describing each sample
and its FASTQ files. :func:`validate_manifest` reads the CSV with pandas,
applies the validation rules described in ``CLAUDE.md`` and returns a clean set
of rows plus warnings and errors.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd
from pydantic import BaseModel, field_validator

REQUIRED_COLUMNS = ("sample_id", "read1")
OPTIONAL_COLUMNS = ("read2", "collection_date", "location", "sample_type")


class ManifestRow(BaseModel):
    """A single validated manifest row."""

    sample_id: str
    read1: str
    read2: str | None = None
    collection_date: date | None = None
    location: str | None = None
    sample_type: str | None = None

    @field_validator("sample_id", "read1")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if value is None or str(value).strip() == "":
            raise ValueError("must not be blank")
        return str(value).strip()

    @field_validator("read2", "location", "sample_type", mode="before")
    @classmethod
    def _blank_to_none(cls, value: Any) -> Any:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @field_validator("collection_date", mode="before")
    @classmethod
    def _parse_date(cls, value: Any) -> Any:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return None
        if isinstance(value, (date, datetime)):
            return value.date() if isinstance(value, datetime) else value
        text = str(value).strip()
        if not text:
            return None
        try:
            return datetime.strptime(text, "%Y-%m-%d").date()
        except ValueError as exc:  # surfaced as a pydantic validation error
            raise ValueError(f"collection_date '{text}' is not in YYYY-MM-DD format") from exc


class ManifestValidationResult(BaseModel):
    """Structured result of validating a manifest."""

    rows: list[ManifestRow]
    warnings: list[str]
    errors: list[str]
    summary: dict[str, Any]

    @property
    def is_valid(self) -> bool:
        return not self.errors


def validate_manifest(
    manifest_path: str | Path,
    *,
    sequencing_type: str = "paired_end",
    dry_run: bool = True,
    remote_data: bool = False,
) -> ManifestValidationResult:
    """Validate a sample manifest CSV.

    Rules enforced:

    * required columns ``sample_id`` and ``read1`` must be present;
    * ``sample_id`` values must be unique and non-blank;
    * for paired-end mode ``read2`` is required for every sample;
    * ``collection_date`` (if present) must parse as ``YYYY-MM-DD``;
    * in real (non-dry-run) mode the referenced FASTQ files must exist.
    """

    manifest_path = Path(manifest_path)
    warnings: list[str] = []
    errors: list[str] = []

    if not manifest_path.exists():
        return ManifestValidationResult(
            rows=[],
            warnings=[],
            errors=[f"Manifest file not found: {manifest_path}"],
            summary={},
        )

    df = pd.read_csv(manifest_path, dtype=str).fillna("")

    missing_cols = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing_cols:
        errors.append(f"Manifest missing required columns: {missing_cols}")
        return ManifestValidationResult(rows=[], warnings=warnings, errors=errors, summary={})

    paired = sequencing_type == "paired_end"
    has_read2_col = "read2" in df.columns

    # Duplicate sample id detection.
    ids = [str(v).strip() for v in df["sample_id"].tolist()]
    seen: set[str] = set()
    dupes: set[str] = set()
    for sid in ids:
        if sid in seen:
            dupes.add(sid)
        seen.add(sid)
    if dupes:
        errors.append(f"Duplicate sample_id values: {sorted(dupes)}")

    rows: list[ManifestRow] = []
    for idx, record in df.iterrows():
        record = record.to_dict()
        try:
            row = ManifestRow(
                sample_id=record.get("sample_id", ""),
                read1=record.get("read1", ""),
                read2=record.get("read2") if has_read2_col else None,
                collection_date=record.get("collection_date") if "collection_date" in df.columns else None,
                location=record.get("location") if "location" in df.columns else None,
                sample_type=record.get("sample_type") if "sample_type" in df.columns else None,
            )
        except Exception as exc:  # pydantic ValidationError or value errors
            errors.append(f"Row {idx + 1}: {exc}")
            continue

        if paired and not row.read2:
            errors.append(f"Sample '{row.sample_id}': read2 is required for paired_end mode")

        if remote_data:
            pass  # paths live on the HPC; local existence is not required
        elif not dry_run:
            for label, fp in (("read1", row.read1), ("read2", row.read2)):
                if fp and not Path(fp).exists():
                    errors.append(f"Sample '{row.sample_id}': {label} file not found: {fp}")
        else:
            for label, fp in (("read1", row.read1), ("read2", row.read2)):
                if fp and not Path(fp).exists():
                    warnings.append(
                        f"Sample '{row.sample_id}': {label} file not found (allowed in dry-run): {fp}"
                    )

        rows.append(row)

    locations = sorted({r.location for r in rows if r.location})
    dates = sorted({r.collection_date.isoformat() for r in rows if r.collection_date})
    summary = {
        "n_samples": len(rows),
        "sequencing_type": sequencing_type,
        "locations": locations,
        "collection_dates": dates,
        "columns": list(df.columns),
    }

    return ManifestValidationResult(rows=rows, warnings=warnings, errors=errors, summary=summary)
