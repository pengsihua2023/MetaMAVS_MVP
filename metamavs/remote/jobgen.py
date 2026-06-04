"""Build the remote SLURM job DAG (one job per bioinformatics step).

Generates a :class:`RemoteJobSpec` per step (qc -> host_removal ->
viral_detection; novel_virus depends on host_removal), renders a self-contained
SLURM script for each, and records the **remote** output paths that
``result_sync`` will download and the parsers will read.

Note: the payload commands are representative tool invocations referencing the
remote inputs/outputs; on a real cluster they are the integration point to
finalize per-tool flags/databases. The output-path contract (filenames below)
is what drives sync + parsing and must stay stable.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from ..utils.file_utils import write_text
from .types import RemoteJobSpec, ResourceSpec


def _samples(state: dict) -> list[dict[str, Any]]:
    path = state.get("validated_manifest_path")
    if not path or not Path(path).exists():
        return []
    return pd.read_csv(path, dtype=str).fillna("").to_dict(orient="records")


def remote_run_dir(state: dict) -> str:
    hpc = state.get("config", {}).get("hpc", {}) or {}
    base = hpc.get("remote_base", "~/metamavs_runs")
    return f"{base}/metamavs/{state['run_id']}"


def build_job_specs(state: dict) -> list[RemoteJobSpec]:
    """Construct the per-step job specs and write their SLURM scripts locally."""

    from .slurm import render_job_script

    cfg = state.get("config", {}) or {}
    hpc = cfg.get("hpc", {}) or {}
    tools_cfg = cfg.get("tools", {}) or {}
    run_dir = Path(state["run_dir"])
    rrun = remote_run_dir(state)
    res_defaults = dict(partition=hpc.get("partition", "batch"))
    modules = hpc.get("modules", [])
    conda_env = hpc.get("conda_env")
    scripts_local = run_dir / "remote" / "scripts"
    log_dir = f"{rrun}/logs"

    samples = _samples(state)
    specs: list[RemoteJobSpec] = []

    def finalize(spec: RemoteJobSpec) -> RemoteJobSpec:
        spec.modules = modules
        spec.conda_env = conda_env
        script = render_job_script(spec, log_dir=log_dir)
        write_text(spec.script_local, script)
        return spec

    # --- qc ---------------------------------------------------------------
    qc_out, qc_cmds = [], [f"mkdir -p {rrun}/results/qc"]
    for s in samples:
        sid, r1, r2 = s["sample_id"], s.get("read1", ""), s.get("read2", "")
        qc_out.append(f"{rrun}/results/qc/{sid}.fastqc_data.txt")
        qc_cmds.append(f"fastqc -t {cfg.get('execution', {}).get('threads', 8)} -o {rrun}/results/qc {r1} {r2}".strip())
    specs.append(finalize(RemoteJobSpec(
        job_name="qc", step="qc", payload=qc_cmds, output_files=qc_out,
        script_local=str(scripts_local / "qc.sh"), script_remote=f"{rrun}/scripts/qc.sh",
        resources=ResourceSpec(**res_defaults),
    )))

    # --- host_removal (depends qc) ---------------------------------------
    hr = tools_cfg.get("host_removal", {})
    tool = hr.get("tool", "bowtie2")
    ref = hr.get("host_reference") or "$HOST_REF"
    hr_out, hr_cmds = [], [f"mkdir -p {rrun}/results/host_removal"]
    for s in samples:
        sid, r1, r2 = s["sample_id"], s.get("read1", ""), s.get("read2", "")
        bam = f"{rrun}/work/{sid}.host.bam"
        hr_cmds.append(f"{tool} -x {ref} -1 {r1} -2 {r2} | samtools view -bS - > {bam}")
        hr_cmds.append(f"samtools flagstat {bam} > {rrun}/results/host_removal/{sid}.flagstat")
        hr_out.append(f"{rrun}/results/host_removal/{sid}.flagstat")
    specs.append(finalize(RemoteJobSpec(
        job_name="host_removal", step="host_removal", payload=hr_cmds, output_files=hr_out,
        depends_on=["qc"], script_local=str(scripts_local / "host_removal.sh"),
        script_remote=f"{rrun}/scripts/host_removal.sh", resources=ResourceSpec(**res_defaults),
    )))

    # --- viral_detection (depends host_removal) --------------------------
    vd = tools_cfg.get("viral_detection", {})
    k2db = vd.get("kraken2_db") or "$KRAKEN2_DB"
    vd_out, vd_cmds = [], [f"mkdir -p {rrun}/results/viral_detection"]
    for s in samples:
        sid = s["sample_id"]
        rep = f"{rrun}/results/viral_detection/{sid}.kraken2.report"
        vd_cmds.append(f"kraken2 --db {k2db} --report {rep} --output {rrun}/work/{sid}.k2.out "
                       f"--paired {rrun}/work/{sid}_nonhost_R1.fastq.gz {rrun}/work/{sid}_nonhost_R2.fastq.gz")
        vd_cmds.append(f"bracken -d {k2db} -i {rep} -o {rrun}/results/viral_detection/{sid}.bracken -r 150 -l S")
        vd_out += [rep, f"{rrun}/results/viral_detection/{sid}.bracken"]
    specs.append(finalize(RemoteJobSpec(
        job_name="viral_detection", step="viral_detection", payload=vd_cmds, output_files=vd_out,
        depends_on=["host_removal"], script_local=str(scripts_local / "viral_detection.sh"),
        script_remote=f"{rrun}/scripts/viral_detection.sh", resources=ResourceSpec(**res_defaults),
    )))

    # --- novel_virus (depends host_removal) ------------------------------
    nv = tools_cfg.get("novel_virus_screening", {})
    if nv.get("enabled", True):
        nv_out, nv_cmds = [], [f"mkdir -p {rrun}/results/novel_virus"]
        for s in samples:
            sid = s["sample_id"]
            nv_cmds.append(f"megahit -1 {rrun}/work/{sid}_nonhost_R1.fastq.gz "
                           f"-2 {rrun}/work/{sid}_nonhost_R2.fastq.gz -o {rrun}/work/{sid}.assembly")
            nv_cmds.append(f"checkv end_to_end {rrun}/work/{sid}.assembly/final.contigs.fa "
                           f"{rrun}/work/{sid}.checkv")
            nv_cmds.append(f"cp {rrun}/work/{sid}.checkv/quality_summary.tsv "
                           f"{rrun}/results/novel_virus/{sid}.checkv_quality_summary.tsv")
            nv_out.append(f"{rrun}/results/novel_virus/{sid}.checkv_quality_summary.tsv")
        specs.append(finalize(RemoteJobSpec(
            job_name="novel_virus", step="novel_virus", payload=nv_cmds, output_files=nv_out,
            depends_on=["host_removal"], script_local=str(scripts_local / "novel_virus.sh"),
            script_remote=f"{rrun}/scripts/novel_virus.sh", resources=ResourceSpec(**res_defaults),
        )))

    return specs
