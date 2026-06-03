"""Configuration schema and YAML loader for MetaMAVS.

The full configuration is validated with pydantic so that malformed configs
fail early with clear messages. ``load_config`` reads a YAML file and returns a
validated :class:`MetaMAVSConfig`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator


class ProjectConfig(BaseModel):
    name: str = "MetaMAVS"
    run_name: str = "example_run"
    output_dir: str = "reports/example_run"


class InputConfig(BaseModel):
    manifest: str
    sequencing_type: Literal["paired_end", "single_end"] = "paired_end"


class ExecutionConfig(BaseModel):
    dry_run: bool = True
    mode: Literal["local", "slurm"] = "local"
    threads: int = Field(default=8, ge=1)


class QCToolsConfig(BaseModel):
    fastqc: bool = True
    fastp: bool = True
    multiqc: bool = True


class HostRemovalConfig(BaseModel):
    tool: Literal["bowtie2", "bwa", "minimap2"] = "bowtie2"
    host_reference: str | None = None


class ViralDetectionConfig(BaseModel):
    tools: list[str] = Field(default_factory=lambda: ["kraken2", "diamond"])
    kraken2_db: str | None = None
    diamond_db: str | None = None


class AssemblyConfig(BaseModel):
    enabled: bool = True
    assembler: Literal["megahit", "metaspades"] = "megahit"


class NovelVirusConfig(BaseModel):
    enabled: bool = True
    tools: list[str] = Field(default_factory=lambda: ["virsorter2", "checkv"])


class ToolsConfig(BaseModel):
    qc: QCToolsConfig = Field(default_factory=QCToolsConfig)
    host_removal: HostRemovalConfig = Field(default_factory=HostRemovalConfig)
    viral_detection: ViralDetectionConfig = Field(default_factory=ViralDetectionConfig)
    assembly: AssemblyConfig = Field(default_factory=AssemblyConfig)
    novel_virus_screening: NovelVirusConfig = Field(default_factory=NovelVirusConfig)


class RiskConfig(BaseModel):
    high_risk_pathogens: list[str] = Field(
        default_factory=lambda: [
            "SARS-CoV-2",
            "Influenza A virus",
            "Influenza B virus",
            "Norovirus",
            "Enterovirus",
        ]
    )
    review_on_high_risk: bool = True
    review_on_novel_candidates: bool = True
    review_on_qc_failure: bool = True


class ReportConfig(BaseModel):
    formats: list[str] = Field(default_factory=lambda: ["markdown", "html"])

    @field_validator("formats")
    @classmethod
    def _validate_formats(cls, value: list[str]) -> list[str]:
        allowed = {"markdown", "html"}
        bad = set(value) - allowed
        if bad:
            raise ValueError(f"Unsupported report formats: {sorted(bad)}; allowed: {sorted(allowed)}")
        return value


class MetaMAVSConfig(BaseModel):
    """Top-level validated configuration object."""

    project: ProjectConfig = Field(default_factory=ProjectConfig)
    input: InputConfig
    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)
    report: ReportConfig = Field(default_factory=ReportConfig)


def load_config(path: str | Path) -> MetaMAVSConfig:
    """Load and validate a MetaMAVS YAML config file.

    Raises
    ------
    FileNotFoundError
        If the config file does not exist.
    ValueError
        If the YAML is empty or not a mapping.
    pydantic.ValidationError
        If the config fails schema validation.
    """

    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)

    if raw is None:
        raise ValueError(f"Config file is empty: {path}")
    if not isinstance(raw, dict):
        raise ValueError(f"Config root must be a mapping, got {type(raw).__name__}: {path}")

    return MetaMAVSConfig.model_validate(raw)
