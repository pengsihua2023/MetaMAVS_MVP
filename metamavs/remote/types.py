"""Pydantic data structures for the Phase 3 remote-execution subsystem."""

from __future__ import annotations

from pydantic import BaseModel, Field

# SLURM states considered terminal (job has finished, one way or another).
TERMINAL_STATES = {"COMPLETED", "FAILED", "TIMEOUT", "CANCELLED", "OUT_OF_MEMORY", "NODE_FAIL"}


class ResourceSpec(BaseModel):
    partition: str = "batch"
    cpus: int = 8
    mem: str = "32G"
    time: str = "24:00:00"


class RemoteJobSpec(BaseModel):
    """Everything needed to stage, submit and collect one SLURM job."""

    job_name: str
    step: str
    sample_id: str | None = None
    script_local: str                       # generated script on the local FS
    script_remote: str                      # where it lives on the HPC
    payload: list[str] = Field(default_factory=list)   # the tool command lines
    input_files: list[str] = Field(default_factory=list)   # local files to upload (if any)
    output_files: list[str] = Field(default_factory=list)  # expected remote outputs to fetch
    depends_on: list[str] = Field(default_factory=list)     # job_names (afterok DAG)
    resources: ResourceSpec = Field(default_factory=ResourceSpec)
    modules: list[str] = Field(default_factory=list)
    conda_env: str | None = None


class SlurmJobStatus(BaseModel):
    job_name: str
    job_id: str | None = None
    state: str = "UNKNOWN"
    exit_code: str | None = None
    submit_time: str | None = None
    end_time: str | None = None
    raw: str = ""

    @property
    def is_terminal(self) -> bool:
        return self.state in TERMINAL_STATES

    @property
    def ok(self) -> bool:
        if self.state != "COMPLETED":
            return False
        if self.exit_code is None:
            return True
        return self.exit_code.split(":")[0] in {"0", ""}


class RemoteExecutionResult(BaseModel):
    run_id: str
    remote_base: str = ""
    jobs: list[SlurmJobStatus] = Field(default_factory=list)
    all_ok: bool = False
    failed: list[str] = Field(default_factory=list)


class SyncedFile(BaseModel):
    remote_path: str
    local_path: str
    size: int = 0
    ok: bool = False


class SyncedResultManifest(BaseModel):
    run_id: str
    downloaded: list[SyncedFile] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    complete: bool = False


class ToolOutputParseResult(BaseModel):
    tool: str
    sample_id: str | None = None
    parsed_table_path: str | None = None
    n_records: int = 0
    ok: bool = True
    schema_version: str = "1"
    warnings: list[str] = Field(default_factory=list)
