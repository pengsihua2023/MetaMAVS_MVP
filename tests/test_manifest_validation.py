"""Tests for manifest validation rules."""

from __future__ import annotations

import textwrap

from metamavs.schemas import validate_manifest


def _write(tmp_path, content: str):
    p = tmp_path / "manifest.csv"
    p.write_text(textwrap.dedent(content).strip() + "\n")
    return p


def test_valid_paired_end_manifest(tmp_path):
    p = _write(
        tmp_path,
        """
        sample_id,read1,read2,collection_date,location,sample_type
        s1,a_R1.fq.gz,a_R2.fq.gz,2026-01-01,site_A,wastewater
        s2,b_R1.fq.gz,b_R2.fq.gz,2026-01-08,site_A,wastewater
        """,
    )
    result = validate_manifest(p, sequencing_type="paired_end", dry_run=True)
    assert result.is_valid
    assert result.summary["n_samples"] == 2
    assert result.summary["locations"] == ["site_A"]


def test_duplicate_sample_ids_rejected(tmp_path):
    p = _write(
        tmp_path,
        """
        sample_id,read1,read2
        s1,a_R1.fq.gz,a_R2.fq.gz
        s1,b_R1.fq.gz,b_R2.fq.gz
        """,
    )
    result = validate_manifest(p, sequencing_type="paired_end", dry_run=True)
    assert not result.is_valid
    assert any("Duplicate" in e for e in result.errors)


def test_paired_end_requires_read2(tmp_path):
    p = _write(
        tmp_path,
        """
        sample_id,read1,read2
        s1,a_R1.fq.gz,
        """,
    )
    result = validate_manifest(p, sequencing_type="paired_end", dry_run=True)
    assert not result.is_valid
    assert any("read2 is required" in e for e in result.errors)


def test_single_end_allows_missing_read2(tmp_path):
    p = _write(
        tmp_path,
        """
        sample_id,read1
        s1,a.fq.gz
        """,
    )
    result = validate_manifest(p, sequencing_type="single_end", dry_run=True)
    assert result.is_valid
    assert result.summary["n_samples"] == 1


def test_missing_required_column(tmp_path):
    p = _write(
        tmp_path,
        """
        sample_id,collection_date
        s1,2026-01-01
        """,
    )
    result = validate_manifest(p, sequencing_type="single_end", dry_run=True)
    assert not result.is_valid
    assert any("missing required columns" in e for e in result.errors)


def test_bad_date_format_rejected(tmp_path):
    p = _write(
        tmp_path,
        """
        sample_id,read1,collection_date
        s1,a.fq.gz,01/01/2026
        """,
    )
    result = validate_manifest(p, sequencing_type="single_end", dry_run=True)
    assert not result.is_valid
    assert any("collection_date" in e for e in result.errors)


def test_missing_files_warn_in_dry_run(tmp_path):
    p = _write(
        tmp_path,
        """
        sample_id,read1
        s1,nonexistent.fq.gz
        """,
    )
    result = validate_manifest(p, sequencing_type="single_end", dry_run=True)
    assert result.is_valid
    assert any("not found" in w for w in result.warnings)


def test_missing_files_error_in_real_mode(tmp_path):
    p = _write(
        tmp_path,
        """
        sample_id,read1
        s1,nonexistent.fq.gz
        """,
    )
    result = validate_manifest(p, sequencing_type="single_end", dry_run=False)
    assert not result.is_valid
    assert any("not found" in e for e in result.errors)
