"""Tests for YAML config loading and validation."""

from __future__ import annotations

import pytest
import yaml

from metamavs.config import MetaMAVSConfig, load_config


def test_load_example_config():
    cfg = load_config("configs/example_config.yaml")
    assert isinstance(cfg, MetaMAVSConfig)
    assert cfg.project.name == "MetaMAVS"
    assert cfg.input.sequencing_type == "paired_end"
    assert cfg.execution.dry_run is True
    assert "kraken2" in cfg.tools.viral_detection.tools
    assert "SARS-CoV-2" in cfg.risk.high_risk_pathogens


def test_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        load_config("configs/does_not_exist.yaml")


def test_empty_config_raises(tmp_path):
    p = tmp_path / "empty.yaml"
    p.write_text("")
    with pytest.raises(ValueError):
        load_config(p)


def test_invalid_sequencing_type_raises(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text(yaml.safe_dump({"input": {"manifest": "m.csv", "sequencing_type": "triple_end"}}))
    with pytest.raises(Exception):  # pydantic ValidationError
        load_config(p)


def test_invalid_report_format_raises(tmp_path):
    p = tmp_path / "bad_report.yaml"
    p.write_text(
        yaml.safe_dump({"input": {"manifest": "m.csv"}, "report": {"formats": ["pdf"]}})
    )
    with pytest.raises(Exception):
        load_config(p)


def test_defaults_applied_with_minimal_config(tmp_path):
    p = tmp_path / "min.yaml"
    p.write_text(yaml.safe_dump({"input": {"manifest": "m.csv"}}))
    cfg = load_config(p)
    assert cfg.execution.threads == 8
    assert cfg.tools.host_removal.tool == "bowtie2"
    assert cfg.report.formats == ["markdown", "html"]
