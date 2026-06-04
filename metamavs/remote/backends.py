"""Remote backends: the abstraction that makes Phase 3 testable without a cluster.

``SSHBackend`` talks to a real HPC via subprocess ``ssh``/``rsync``/``sbatch``/
``sacct``. ``MockBackend`` fakes a cluster on the local filesystem (placing
fixture outputs on submit), so the whole pipeline runs in tests with no SSH.
"""

from __future__ import annotations

import shutil
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path

from ..utils.logging_utils import get_logger
from .slurm import build_sbatch_command, parse_sacct
from .types import RemoteJobSpec, SlurmJobStatus

logger = get_logger("remote.backends")


class RemoteBackend(ABC):
    """Interface for staging, submitting and collecting remote jobs."""

    @abstractmethod
    def run(self, command: str) -> tuple[int, str, str]:
        """Run a shell command remotely; return (returncode, stdout, stderr)."""

    @abstractmethod
    def upload(self, local: str, remote: str) -> bool: ...

    @abstractmethod
    def download(self, remote: str, local: str) -> bool: ...

    @abstractmethod
    def exists(self, remote_path: str) -> bool: ...

    @abstractmethod
    def submit(self, spec: RemoteJobSpec, dep_job_ids: list[str]) -> str:
        """Submit one job (with afterok dependencies); return its job id."""

    @abstractmethod
    def statuses(self, name_to_id: dict[str, str]) -> list[SlurmJobStatus]: ...


# --------------------------------------------------------------------------- #
class SSHBackend(RemoteBackend):
    """Real HPC backend over subprocess ssh + rsync + SLURM."""

    def __init__(self, host: str, user: str | None = None, ssh_opts: list[str] | None = None, retries: int = 3):
        self.host = host
        self.target = f"{user}@{host}" if user else host
        self.ssh_opts = ssh_opts or []
        self.retries = retries

    def _ssh(self, command: str) -> tuple[int, str, str]:
        argv = ["ssh", *self.ssh_opts, self.target, command]
        proc = subprocess.run(argv, capture_output=True, text=True)  # noqa: S603
        return proc.returncode, proc.stdout, proc.stderr

    def run(self, command: str) -> tuple[int, str, str]:
        last = (1, "", "not attempted")
        for attempt in range(1, self.retries + 2):
            last = self._ssh(command)
            if last[0] == 0:
                return last
            logger.warning("ssh attempt %d failed: %s", attempt, last[2].strip()[:200])
        return last

    def _rsync(self, src: str, dst: str) -> bool:
        argv = ["rsync", "-avz", "--partial", "--checksum", src, dst]
        for attempt in range(1, self.retries + 2):
            proc = subprocess.run(argv, capture_output=True, text=True)  # noqa: S603
            if proc.returncode == 0:
                return True
            logger.warning("rsync attempt %d failed: %s", attempt, proc.stderr.strip()[:200])
        return False

    def upload(self, local: str, remote: str) -> bool:
        self.run(f"mkdir -p {str(Path(remote).parent)}")
        return self._rsync(local, f"{self.target}:{remote}")

    def download(self, remote: str, local: str) -> bool:
        Path(local).parent.mkdir(parents=True, exist_ok=True)
        return self._rsync(f"{self.target}:{remote}", local)

    def exists(self, remote_path: str) -> bool:
        rc, _, _ = self.run(f"test -e {remote_path}")
        return rc == 0

    def submit(self, spec: RemoteJobSpec, dep_job_ids: list[str]) -> str:
        cmd = build_sbatch_command(spec.script_remote, dep_job_ids)
        rc, out, err = self.run(cmd)
        if rc != 0:
            raise RuntimeError(f"sbatch failed for {spec.job_name}: {err.strip()}")
        return out.strip().split(";")[0]  # `--parsable` -> "<jobid>[;cluster]"

    def statuses(self, name_to_id: dict[str, str]) -> list[SlurmJobStatus]:
        ids = ",".join(name_to_id.values())
        if not ids:
            return []
        rc, out, _ = self.run(
            f"sacct -j {ids} --parsable2 --noheader --format=JobID,JobName,State,ExitCode"
        )
        parsed = parse_sacct(out) if rc == 0 else []
        by_id = {s.job_id: s for s in parsed}
        result: list[SlurmJobStatus] = []
        for name, jid in name_to_id.items():
            st = by_id.get(jid) or SlurmJobStatus(job_name=name, job_id=jid, state="UNKNOWN")
            st.job_name = name
            result.append(st)
        return result


# --------------------------------------------------------------------------- #
class MockBackend(RemoteBackend):
    """Fake HPC on the local filesystem for tests / offline development.

    On :meth:`submit`, fixture files whose name is a substring of an expected
    output path are copied into the fake-remote tree, so :meth:`download` later
    yields realistic tool outputs. ``fail_jobs`` forces FAILED status for the
    named jobs (to exercise recovery paths).
    """

    def __init__(self, root: str | Path, fixtures: dict[str, str] | None = None, fail_jobs: set[str] | None = None):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.fixtures = fixtures or {}
        self.fail_jobs = fail_jobs or set()
        self._counter = 0
        self._submitted: dict[str, str] = {}  # job_id -> job_name

    def _map(self, remote: str) -> Path:
        return self.root / str(remote).lstrip("/")

    def run(self, command: str) -> tuple[int, str, str]:
        if command.strip().startswith("mkdir -p"):
            target = command.split("mkdir -p", 1)[1].strip()
            self._map(target).mkdir(parents=True, exist_ok=True)
        return 0, "", ""

    def upload(self, local: str, remote: str) -> bool:
        dst = self._map(remote)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(local, dst)
        return True

    def download(self, remote: str, local: str) -> bool:
        src = self._map(remote)
        if not src.exists():
            return False
        Path(local).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(src, local)
        return True

    def exists(self, remote_path: str) -> bool:
        return self._map(remote_path).exists()

    def submit(self, spec: RemoteJobSpec, dep_job_ids: list[str]) -> str:
        self._counter += 1
        job_id = f"mock-{self._counter}"
        self._submitted[job_id] = spec.job_name
        # Place fixture outputs (substring match against each expected output).
        for out in spec.output_files:
            base = Path(out).name
            for token, fixture in self.fixtures.items():
                if token in base and Path(fixture).exists():
                    dst = self._map(out)
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy(fixture, dst)
                    break
        return job_id

    def statuses(self, name_to_id: dict[str, str]) -> list[SlurmJobStatus]:
        out = []
        for name, jid in name_to_id.items():
            if name in self.fail_jobs:
                out.append(SlurmJobStatus(job_name=name, job_id=jid, state="FAILED", exit_code="1:0"))
            else:
                out.append(SlurmJobStatus(job_name=name, job_id=jid, state="COMPLETED", exit_code="0:0"))
        return out


# --------------------------------------------------------------------------- #
def make_backend(state: dict) -> RemoteBackend:
    """Build the backend selected by ``config.hpc.backend`` (ssh | mock)."""

    cfg = state.get("config", {}) or {}
    hpc = cfg.get("hpc", {}) or {}
    backend = hpc.get("backend", "ssh")

    if backend == "mock":
        root = Path(state["run_dir"]) / "remote" / "_mock_hpc"
        fixtures: dict[str, str] = {}
        fx_dir = hpc.get("mock_fixtures_dir")
        if fx_dir and Path(fx_dir).is_dir():
            fixtures = {p.name: str(p) for p in Path(fx_dir).iterdir() if p.is_file()}
        return MockBackend(root=root, fixtures=fixtures, fail_jobs=set(hpc.get("mock_fail_jobs", [])))

    host = hpc.get("host")
    if not host:
        raise ValueError("hpc.host must be set for the ssh backend")
    opts: list[str] = []
    return SSHBackend(host=host, user=hpc.get("user"), ssh_opts=opts, retries=int(hpc.get("retries", 3)))
