"""Tool output parsers: raw HPC tool outputs -> MetaMAVS normalized tables.

Each parser is pure-local and defensive: on malformed input it returns a
``ToolOutputParseResult(ok=False, warnings=[...])`` rather than raising, so one
bad file never crashes the pipeline (graceful degradation, consistent with
Phases 1-2).
"""

from __future__ import annotations

from .checkv import parse_checkv
from .diamond import parse_diamond
from .fastqc import parse_fastqc
from .host_removal import parse_flagstat
from .kraken2 import parse_bracken, parse_kraken2

# Registry keyed by an output-filename token (substring match by the agent).
PARSERS = {
    "fastqc_data.txt": ("fastqc", parse_fastqc),
    "flagstat": ("host_removal", parse_flagstat),
    "kraken2.report": ("kraken2", parse_kraken2),
    "bracken": ("bracken", parse_bracken),
    "diamond.tsv": ("diamond", parse_diamond),
    "checkv": ("checkv", parse_checkv),
}

__all__ = [
    "PARSERS",
    "parse_fastqc",
    "parse_flagstat",
    "parse_kraken2",
    "parse_bracken",
    "parse_diamond",
    "parse_checkv",
]
