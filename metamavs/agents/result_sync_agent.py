"""result_sync_agent: download remote outputs to local, verify integrity."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..remote.backends import make_backend
from ..remote.types import RemoteJobSpec, SyncedFile, SyncedResultManifest
from ..state import MetaMAVSState
from ..utils.file_utils import write_json
from ..utils.logging_utils import get_logger

logger = get_logger("agents.result_sync")


def result_sync_agent_node(state: MetaMAVSState) -> dict[str, Any]:
    """Download each job's expected outputs into ``results/raw/<step>/``."""

    logger.info("Result sync: downloading HPC outputs")
    run_dir = Path(state["run_dir"])
    specs = [RemoteJobSpec(**s) for s in state.get("remote_job_specs", []) or []]
    if not specs:
        warn = "result_sync: no remote_job_specs to download"
        return {"synced_manifest": {}, "warnings": [warn], "execution_log": [warn]}

    backend = make_backend(state)
    manifest = SyncedResultManifest(run_id=state["run_id"])
    raw_root = run_dir / "results" / "raw"

    for spec in specs:
        for remote in spec.output_files:
            local = raw_root / spec.step / Path(remote).name
            ok = backend.download(remote, str(local))
            size = local.stat().st_size if (ok and local.exists()) else 0
            ok = ok and size > 0
            manifest.downloaded.append(SyncedFile(remote_path=remote, local_path=str(local), size=size, ok=ok))
            if not ok:
                manifest.missing.append(remote)

    manifest.complete = not manifest.missing
    write_json(run_dir / "results" / "synced_manifest.json", manifest.model_dump())

    warnings: list[str] = []
    if manifest.missing:
        warnings.append(f"result_sync: {len(manifest.missing)} expected output(s) missing/empty after download")
    logger.info("Result sync: %d file(s), complete=%s", len(manifest.downloaded), manifest.complete)

    return {
        "synced_manifest": manifest.model_dump(),
        "warnings": warnings,
        "execution_log": [f"result_sync: {len(manifest.downloaded)} file(s), complete={manifest.complete}"],
    }
