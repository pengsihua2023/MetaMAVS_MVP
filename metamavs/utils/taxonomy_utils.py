"""Helpers for taxonomy normalisation and false-positive heuristics.

These are deterministic, rule-based heuristics suitable for the Phase 1
prototype. In later phases an LLM reasoning step can replace or augment the
``flag_false_positive`` logic for nuanced interpretation.
"""

from __future__ import annotations

from typing import Any

# Keywords that suggest a hit is an environmental bacteriophage rather than a
# human/animal pathogen. Phages are extremely common in wastewater and should
# be reported separately so they do not inflate pathogen risk.
PHAGE_KEYWORDS = ("phage", "siphoviridae", "myoviridae", "podoviridae", "microviridae")

# Read-count floor below which a detection is considered low-confidence.
LOW_READ_COUNT_THRESHOLD = 10

# Minimum fraction of distinct k-mers / unique reads expected for a real hit.
LOW_COMPLEXITY_CONFIDENCE = 0.30


def is_phage(taxon_name: str) -> bool:
    """Return True if the taxon name looks like a bacteriophage."""

    name = taxon_name.lower()
    return any(keyword in name for keyword in PHAGE_KEYWORDS)


def flag_false_positive(hit: dict[str, Any]) -> tuple[bool, list[str]]:
    """Apply heuristics to decide whether a viral hit is a likely false positive.

    Returns a ``(is_flagged, reasons)`` tuple. A hit may be flagged for being a
    phage, having very few supporting reads, or having low classification
    confidence (a proxy for low-complexity / spurious mapping).
    """

    reasons: list[str] = []

    name = str(hit.get("taxon_name", ""))
    reads = int(hit.get("reads", 0))
    confidence = float(hit.get("confidence", 1.0))

    if is_phage(name):
        reasons.append("environmental_phage")
    if reads < LOW_READ_COUNT_THRESHOLD:
        reasons.append("low_read_count")
    if confidence < LOW_COMPLEXITY_CONFIDENCE:
        reasons.append("low_confidence_or_complexity")

    return (len(reasons) > 0, reasons)


def rank_label(rank: str) -> str:
    """Normalise a taxonomic rank string to a canonical lowercase label."""

    return (rank or "unknown").strip().lower()
