"""Execution backends for the MetaMAVS workflow (local now, SLURM later)."""

from .local_workflow import run_local_workflow

__all__ = ["run_local_workflow"]
