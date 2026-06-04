"""Tests for tool-output parsers against real-format fixtures."""

from __future__ import annotations

from pathlib import Path

from metamavs.parsers import (
    parse_bracken,
    parse_checkv,
    parse_fastqc,
    parse_flagstat,
    parse_kraken2,
)

FIX = Path(__file__).parent / "fixtures"


def test_parse_fastqc():
    out = parse_fastqc(str(FIX / "fastqc_data.txt"), "s1")
    assert out["result"].ok
    s = out["summary"]
    assert s["total_reads"] == 2000000
    assert s["mean_read_length"] == 150
    assert 34.0 <= s["mean_quality"] <= 37.0  # averaged per-base means


def test_parse_flagstat():
    out = parse_flagstat(str(FIX / "flagstat"), "s1")
    assert out["result"].ok
    s = out["summary"]
    assert s["host_read_pct"] == 85.0
    assert s["non_host_reads"] == 300000


def test_parse_kraken2():
    out = parse_kraken2(str(FIX / "kraken2.report"), "s1")
    assert out["result"].ok
    names = {r["taxon_name"] for r in out["records"]}
    assert "Influenza A virus" in names
    # only species (rank S) rows -> "root" excluded
    assert "root" not in names
    flu = next(r for r in out["records"] if r["taxon_name"] == "Influenza A virus")
    assert flu["reads"] == 3600
    assert flu["family"] == "Orthomyxoviridae"


def test_parse_bracken():
    out = parse_bracken(str(FIX / "bracken"), "s1")
    assert out["result"].ok
    rec = {r["taxon_name"]: r for r in out["records"]}
    assert rec["Influenza A virus"]["reads"] == 3600   # new_est_reads
    assert rec["Norovirus"]["reads"] == 2480


def test_parse_checkv():
    out = parse_checkv(str(FIX / "checkv_quality_summary.tsv"), "s1")
    assert out["result"].ok
    assert out["records"][0]["checkv_quality"] == "High-quality"
    assert out["records"][0]["completeness"] == 95.2


def test_parser_is_defensive_on_garbage(tmp_path):
    bad = tmp_path / "bad.kraken2.report"
    bad.write_text("not\ta\tvalid\nfile")
    out = parse_kraken2(str(bad), "s1")
    # malformed -> ok True but zero usable records (no rank-S lines); never raises
    assert out["records"] == []
