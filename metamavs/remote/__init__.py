"""Remote (HPC) execution subsystem for MetaMAVS Phase 3.

Local controller -> HPC executor -> results repatriated -> parsed locally.
Everything reachable through the :class:`RemoteBackend` abstraction so the whole
pipeline is testable without a real cluster (see ``MockBackend``).
"""

from .backends import MockBackend, RemoteBackend, SSHBackend, make_backend
from .types import (
    RemoteExecutionResult,
    RemoteJobSpec,
    ResourceSpec,
    SlurmJobStatus,
    SyncedFile,
    SyncedResultManifest,
    ToolOutputParseResult,
)

__all__ = [
    "RemoteBackend",
    "SSHBackend",
    "MockBackend",
    "make_backend",
    "ResourceSpec",
    "RemoteJobSpec",
    "SlurmJobStatus",
    "RemoteExecutionResult",
    "SyncedFile",
    "SyncedResultManifest",
    "ToolOutputParseResult",
]
