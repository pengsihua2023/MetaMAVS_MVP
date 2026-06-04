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
    # Phase 3: when True, manifest read1/read2 are paths on the HPC (no upload,
    # and local existence is not required).
    remote_data: bool = False


class ExecutionConfig(BaseModel):
    dry_run: bool = True
    # "hpc" routes bioinformatics steps to a remote SLURM cluster (Phase 3).
    mode: Literal["local", "slurm", "hpc"] = "local"
    threads: int = Field(default=8, ge=1)
    # Phase 2: extra attempts for a failing command before giving up (0 = no retry).
    retries: int = Field(default=0, ge=0)


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
    gottcha2_db: str | None = None
    gottcha2_level: str = "species"


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


class SlurmConfig(BaseModel):
    """SLURM submission parameters (Phase 2 script generation)."""

    partition: str = "batch"
    time: str = "24:00:00"
    mem: str = "32G"
    cpus_per_task: int = Field(default=8, ge=1)
    modules: list[str] = Field(default_factory=list)
    conda_env: str | None = None


class HPCConfig(BaseModel):
    """Remote HPC execution settings (Phase 3)."""

    backend: Literal["ssh", "mock"] = "ssh"
    host: str | None = None
    user: str | None = None
    remote_base: str = "~/metamavs_runs"
    partition: str = "batch"
    # Default SLURM resources for every job (override per step via step_resources).
    cpus: int = Field(default=8, ge=1)
    mem: str = "32G"
    time: str = "24:00:00"
    # Per-step resource overrides, e.g. {"gottcha2": {"mem": "120G", "cpus": 16}}.
    step_resources: dict[str, dict] = Field(default_factory=dict)
    conda_env: str | None = None
    modules: list[str] = Field(default_factory=list)
    # Shell lines prepended to every SLURM script (e.g. source conda profile).
    env_setup: list[str] = Field(default_factory=list)
    # Which remote steps to run (None = derive from tools config). Lets you run a
    # minimal pipeline, e.g. ["gottcha2"]. Valid: qc, host_removal, kraken2,
    # gottcha2, novel_virus.
    steps: list[str] | None = None
    # Per-step environment setup lines (override env_setup). Each tool can use its
    # own conda env, e.g. {"gottcha2": ["export PATH=.../gottcha2_env/bin:$PATH"]}.
    step_env: dict[str, list[str]] = Field(default_factory=dict)
    retries: int = Field(default=3, ge=0)
    poll_interval_s: int = Field(default=30, ge=1)
    max_wait_s: int = Field(default=86400, ge=1)
    # SSH connection multiplexing: authenticate (incl. Duo 2FA) ONCE, then reuse
    # the master connection for every subsequent ssh/rsync invocation.
    ssh_control: bool = True
    ssh_control_path: str = "~/.ssh/metamavs-cm-%r@%h:%p"
    ssh_control_persist: str = "8h"
    ssh_opts: list[str] = Field(default_factory=list)  # extra raw ssh -o options
    # For backend == "mock": directory of fake tool outputs used as fixtures,
    # and an optional list of job_names to force-FAIL (to exercise recovery).
    mock_fixtures_dir: str | None = None
    mock_fail_jobs: list[str] = Field(default_factory=list)


class LLMConfig(BaseModel):
    """Phase 4: optional LLM interpretation (Anthropic Claude). Off by default."""

    enabled: bool = False
    model: str = "claude-opus-4-8"
    effort: Literal["low", "medium", "high", "max"] = "medium"
    max_tokens: int = Field(default=4000, ge=256)


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
    slurm: SlurmConfig = Field(default_factory=SlurmConfig)
    hpc: HPCConfig = Field(default_factory=HPCConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)


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
