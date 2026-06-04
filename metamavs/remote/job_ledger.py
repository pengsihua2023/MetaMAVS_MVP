"""Durable job ledger: persist job ids/paths/states so a restarted controller
can re-attach to running HPC jobs instead of resubmitting them."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class JobLedger:
    """JSON-backed record of a run's remote jobs (``reports/<run>/remote/jobs.json``)."""

    def __init__(self, run_dir: str | Path):
        self.path = Path(run_dir) / "remote" / "jobs.json"
        self.data: dict[str, Any] = {"jobs": {}}
        if self.path.exists():
            try:
                self.data = json.loads(self.path.read_text())
            except Exception:
                self.data = {"jobs": {}}

    def record_ids(self, name_to_id: dict[str, str]) -> None:
        for name, jid in name_to_id.items():
            self.data["jobs"].setdefault(name, {})["job_id"] = jid
        self.save()

    def update_statuses(self, statuses: list[Any]) -> None:
        for s in statuses:
            entry = self.data["jobs"].setdefault(s.job_name, {})
            entry["job_id"] = s.job_id
            entry["state"] = s.state
            entry["exit_code"] = s.exit_code
        self.save()

    def known_ids(self) -> dict[str, str]:
        return {n: e["job_id"] for n, e in self.data["jobs"].items() if e.get("job_id")}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2))
