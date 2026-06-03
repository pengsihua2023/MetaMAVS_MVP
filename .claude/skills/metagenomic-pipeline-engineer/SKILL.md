---
name: metagenomic-pipeline-engineer
description: Use this skill when adding or modifying metagenomic bioinformatics command generation for MetaMAVS.
---

# Metagenomic Pipeline Engineer Skill

MetaMAVS supports dry-run command generation first.

When adding bioinformatics tools:

- Do not require the tool to be installed in dry-run mode.
- Generate reproducible commands.
- Write commands to the run directory.
- Include input paths, output paths, threads, and database paths.
- Validate required config fields.
- Avoid hard-coded absolute paths.
- Do not assume sudo/root access.
- Keep HPC compatibility in mind.

Supported tool categories:

- QC: FastQC, fastp, MultiQC
- Host removal: Bowtie2, BWA, minimap2
- Viral detection: Kraken2, KrakenUniq, Centrifuge, DIAMOND, BLAST
- Assembly: MEGAHIT, metaSPAdes
- Viral contig screening: VirSorter2, VIBRANT, geNomad, CheckV, DeepVirFinder

Scientific caution:

- Low read counts should be flagged.
- Potential contamination should be flagged.
- Do not overstate pathogen detection.
