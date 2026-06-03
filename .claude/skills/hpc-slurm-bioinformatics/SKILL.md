---
name: hpc-slurm-bioinformatics
description: Use this skill when adding HPC, SLURM, Apptainer, or cluster execution support to MetaMAVS.
---

# HPC SLURM Bioinformatics Skill

MetaMAVS should support HPC environments.

Assumptions:

- No sudo/root access.
- Compute nodes may not have internet.
- Use conda/mamba or Apptainer/Singularity.
- Use SLURM for job submission.
- Avoid Docker-only workflows.

When generating SLURM scripts:

- Include job name.
- Include log paths.
- Include CPU, memory, time, and partition options.
- Do not use unsupported SLURM options unless configurable.
- Make paths configurable.
- Use dry-run first.

Example command style:

```bash
sbatch reports/example_run/slurm/metamavs_qc.sbatch
```

Always keep local dry-run mode functional.
