"""abundance_analysis_agent_node: normalise abundance and build trend tables."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from ..state import MetaMAVSState
from ..utils.file_utils import write_csv, write_json
from ..utils.logging_utils import get_logger

logger = get_logger("agents.abundance")

# Marker used for PMMoV (pepper mild mottle virus) normalisation when present.
PMMOV_MARKER = "Pepper mild mottle virus"


def abundance_analysis_agent_node(state: MetaMAVSState) -> dict[str, Any]:
    """Compute reads-per-million (RPM) and genome-length-corrected abundance.

    Builds a per-(sample, taxon) abundance table and a per-taxon trend summary
    comparing the earliest and latest collection dates / samples.
    """

    logger.info("Normalising viral abundance and building trends")
    run_dir = Path(state["run_dir"])
    raw_path = state.get("raw_viral_hits_path")

    if not raw_path or not Path(raw_path).exists():
        warning = "No raw viral hits available for abundance analysis"
        logger.warning(warning)
        return {
            "trend_summary": {"n_taxa": 0},
            "warnings": [warning],
            "execution_log": ["abundance_agent: no hits to analyse"],
        }

    hits = pd.read_csv(raw_path)

    # Per-sample sequencing depth proxy from QC summary (fallback to hit totals).
    qc = state.get("qc_summary", {}) or {}
    depth_by_sample = {
        d["sample_id"]: max(1, int(d.get("total_reads", 0)))
        for d in qc.get("per_sample", [])
    }

    manifest = {}
    mpath = state.get("validated_manifest_path")
    if mpath and Path(mpath).exists():
        for r in pd.read_csv(mpath, dtype=str).fillna("").to_dict(orient="records"):
            manifest[r["sample_id"]] = r

    rows: list[dict[str, Any]] = []
    for _, h in hits.iterrows():
        sid = h["sample_id"]
        reads = int(h["reads"])
        depth = depth_by_sample.get(sid, int(hits[hits["sample_id"] == sid]["reads"].sum()) or 1)
        rpm = reads / depth * 1_000_000
        glen = float(h.get("genome_length_kb", 0) or 0)
        rpkm = (rpm / glen) if glen > 0 else 0.0
        meta = manifest.get(sid, {})
        rows.append(
            {
                "sample_id": sid,
                "taxon_name": h["taxon_name"],
                "reads": reads,
                "rpm": round(rpm, 2),
                "rpkm_genome": round(rpkm, 3),
                "collection_date": meta.get("collection_date", ""),
                "location": meta.get("location", ""),
            }
        )

    abundance_path = write_csv(run_dir / "tables" / "abundance_table.csv", rows)

    # Trend: for each taxon compare first vs last time point by date order.
    df = pd.DataFrame(rows)
    trends: list[dict[str, Any]] = []
    if not df.empty:
        df["_date"] = pd.to_datetime(df["collection_date"], errors="coerce")
        for taxon, g in df.groupby("taxon_name"):
            g = g.sort_values("_date")
            first_rpm = float(g.iloc[0]["rpm"])
            last_rpm = float(g.iloc[-1]["rpm"])
            if first_rpm > 0:
                change = (last_rpm - first_rpm) / first_rpm * 100
            else:
                change = 0.0
            direction = "increasing" if change > 25 else "decreasing" if change < -25 else "stable"
            trends.append(
                {
                    "taxon_name": taxon,
                    "first_rpm": round(first_rpm, 2),
                    "last_rpm": round(last_rpm, 2),
                    "pct_change": round(change, 1),
                    "trend": direction,
                    "mean_rpm": round(float(g["rpm"].mean()), 2),
                }
            )
    trends = sorted(trends, key=lambda d: d["mean_rpm"], reverse=True)
    trend_path = write_csv(run_dir / "tables" / "trend_summary.csv", trends)

    # Lightweight plot specifications (data-only; rendering is downstream/optional).
    plot_specs = {
        "rpm_by_taxon": {
            "type": "bar",
            "x": [t["taxon_name"] for t in trends],
            "y": [t["mean_rpm"] for t in trends],
            "title": "Mean RPM by viral taxon",
        }
    }
    plot_path = write_json(run_dir / "intermediate" / "plot_specs.json", plot_specs)

    sharp = [t["taxon_name"] for t in trends if t["pct_change"] >= 100]
    warnings = []
    if sharp:
        warnings.append(f"Sharp abundance increase (>=100%) for: {', '.join(sharp)}")

    trend_summary = {
        "n_taxa": len(trends),
        "increasing": [t["taxon_name"] for t in trends if t["trend"] == "increasing"],
        "sharp_increase": sharp,
        "top_by_mean_rpm": trends[:5],
    }
    write_json(run_dir / "intermediate" / "trend_summary.json", trend_summary)

    logger.info("Abundance: %d taxa, %d increasing", len(trends), len(trend_summary["increasing"]))

    return {
        "abundance_table_path": str(abundance_path),
        "trend_summary_path": str(trend_path),
        "plot_specs_path": str(plot_path),
        "trend_summary": trend_summary,
        "warnings": warnings,
        "execution_log": [f"abundance_agent: {len(trends)} taxa trend-analysed"],
    }
