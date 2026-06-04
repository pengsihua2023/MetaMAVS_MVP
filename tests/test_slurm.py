"""Tests for SLURM helpers: script rendering, sbatch command, sacct parsing."""

from __future__ import annotations

from metamavs.remote.slurm import build_sbatch_command, parse_sacct, render_job_script
from metamavs.remote.types import RemoteJobSpec, ResourceSpec, SlurmJobStatus


def test_render_job_script():
    spec = RemoteJobSpec(
        job_name="kraken2", step="viral_detection",
        script_local="/tmp/k.sh", script_remote="/remote/k.sh",
        payload=["kraken2 --db DB --report r.txt in.fq"],
        resources=ResourceSpec(partition="gpu", cpus=16, mem="64G", time="12:00:00"),
        modules=["kraken2/2.1.3"], conda_env="tools",
    )
    script = render_job_script(spec, log_dir="/remote/logs")
    assert "#SBATCH --job-name=kraken2" in script
    assert "#SBATCH --partition=gpu" in script
    assert "#SBATCH --cpus-per-task=16" in script
    assert "module load kraken2/2.1.3" in script
    assert "conda activate tools" in script
    assert "kraken2 --db DB" in script


def test_build_sbatch_command_with_deps():
    assert build_sbatch_command("/r/s.sh", []) == "sbatch --parsable /r/s.sh"
    cmd = build_sbatch_command("/r/s.sh", ["101", "102"])
    assert "--dependency=afterok:101:102" in cmd


def test_parse_sacct():
    text = (
        "101|qc|COMPLETED|0:0\n"
        "101.batch|batch|COMPLETED|0:0\n"
        "102|host_removal|FAILED|1:0\n"
    )
    statuses = parse_sacct(text)
    assert len(statuses) == 2  # sub-step 101.batch skipped
    by_name = {s.job_name: s for s in statuses}
    assert by_name["qc"].state == "COMPLETED"
    assert by_name["qc"].ok is True
    assert by_name["host_removal"].state == "FAILED"
    assert by_name["host_removal"].ok is False


def test_slurm_status_terminal_and_ok():
    assert SlurmJobStatus(job_name="x", state="RUNNING").is_terminal is False
    assert SlurmJobStatus(job_name="x", state="COMPLETED", exit_code="0:0").ok is True
    assert SlurmJobStatus(job_name="x", state="TIMEOUT").is_terminal is True
    assert SlurmJobStatus(job_name="x", state="COMPLETED", exit_code="2:0").ok is False
