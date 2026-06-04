"""Non-pathogen control / normalization markers.

Some viruses are detected routinely in wastewater not as threats but as
**process/normalization controls** — most importantly Pepper mild mottle virus
(PMMoV), a plant virus that is the standard faecal-load normalization marker.
These are reported separately (sample-validity / normalization context) and are
**excluded from the risk ranking** so they are not mistaken for pathogens.
"""

from __future__ import annotations

# canonical label -> {taxids, lowercase name patterns}
CONTROL_MARKERS: dict[str, dict] = {
    "Pepper mild mottle virus (PMMoV)": {
        "taxids": {12239},
        "patterns": ["pepper mild mottle", "pmmov"],
        "role": "faecal-load normalization marker (plant virus)",
    },
    "crAssphage": {
        "taxids": {1262072},
        "patterns": ["crassphage", "crass-like"],
        "role": "human faecal indicator (bacteriophage)",
    },
}


def match_control(taxon_name: str, taxid: int) -> str | None:
    """Return the control-marker label this taxon matches, or None."""

    name_l = (taxon_name or "").lower()
    try:
        tid = int(taxid)
    except (TypeError, ValueError):
        tid = 0
    for label, entry in CONTROL_MARKERS.items():
        if tid and tid in entry["taxids"]:
            return label
        if any(pat in name_l for pat in entry["patterns"]):
            return label
    return None


def control_role(label: str) -> str:
    return CONTROL_MARKERS.get(label, {}).get("role", "control marker")
