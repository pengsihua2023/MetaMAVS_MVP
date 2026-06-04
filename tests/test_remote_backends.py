"""Tests for the MockBackend (fake HPC) and submit/poll helpers."""

from __future__ import annotations

from pathlib import Path

from metamavs.remote.backends import MockBackend
from metamavs.remote.slurm import poll_until_terminal, submit_dag
from metamavs.remote.types import RemoteJobSpec

FIX = Path(__file__).parent / "fixtures"


def _spec(name, deps=None, outputs=None):
    return RemoteJobSpec(
        job_name=name, step=name, script_local="/x.sh", script_remote=f"/r/{name}.sh",
        depends_on=deps or [], output_files=outputs or [],
    )


def test_mock_upload_download(tmp_path):
    be = MockBackend(root=tmp_path / "remote")
    src = tmp_path / "a.txt"
    src.write_text("hello")
    assert be.upload(str(src), "/run/a.txt")
    assert be.exists("/run/a.txt")
    dst = tmp_path / "back.txt"
    assert be.download("/run/a.txt", str(dst))
    assert dst.read_text() == "hello"


def test_mock_submit_places_fixtures(tmp_path):
    fixtures = {p.name: str(p) for p in FIX.iterdir() if p.is_file()}
    be = MockBackend(root=tmp_path / "remote", fixtures=fixtures)
    spec = _spec("viral_detection", outputs=["/run/results/s1.kraken2.report", "/run/results/s1.bracken"])
    be.submit(spec, [])
    assert be.exists("/run/results/s1.kraken2.report")
    assert be.exists("/run/results/s1.bracken")


def test_submit_dag_respects_dependencies(tmp_path):
    be = MockBackend(root=tmp_path / "remote")
    specs = [_spec("viral_detection", deps=["host_removal"]),
             _spec("host_removal", deps=["qc"]),
             _spec("qc")]
    name_to_id = submit_dag(be, specs)
    assert set(name_to_id) == {"qc", "host_removal", "viral_detection"}


def test_poll_until_terminal_completes(tmp_path):
    be = MockBackend(root=tmp_path / "remote")
    name_to_id = {"qc": "mock-1", "host_removal": "mock-2"}
    result = poll_until_terminal(be, name_to_id, "run1", interval_s=0, max_wait_s=10, sleep=lambda s: None)
    assert result.all_ok is True
    assert result.failed == []


def test_poll_detects_failure(tmp_path):
    be = MockBackend(root=tmp_path / "remote", fail_jobs={"host_removal"})
    name_to_id = {"qc": "mock-1", "host_removal": "mock-2"}
    result = poll_until_terminal(be, name_to_id, "run1", interval_s=0, max_wait_s=10, sleep=lambda s: None)
    assert result.all_ok is False
    assert "host_removal" in result.failed
