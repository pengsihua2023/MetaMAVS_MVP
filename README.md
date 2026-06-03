# MetaMAVS

**MetaMAVS: Metagenomic Multi-Agent Virus Surveillance System**

A research-grade, **LangGraph-based** multi-agent workflow for viral
surveillance using wastewater, environmental, or clinical metagenomic
sequencing data. Phase 1 is a **deterministic, local, dry-run-capable**
prototype: it requires no cloud services, no paid APIs, no root privileges, and
no external bioinformatics tools.

> ⚠️ **Scientific caution.** MetaMAVS reports *detected sequence signals*, not
> confirmed infections. High-risk detections always require confirmatory
> testing. The system is designed to avoid over-claiming from weak metagenomic
> evidence.

---

## Why LangGraph?

MetaMAVS is **not** a collection of independent Python classes. The workflow is
a stateful [`StateGraph`](https://langchain-ai.github.io/langgraph/): each
analysis step is a node that receives the shared state and returns a partial
update. This gives us conditional routing, a human-in-the-loop checkpoint,
checkpointing, and clean seams where LLM reasoning can later be added.

```text
START
  → input_manager
  → qc_agent
  → host_removal_agent
  → viral_detection_agent
  → taxonomy_agent
  → abundance_agent
  → novel_virus_agent
  → risk_assessment_agent
  → (conditional) ─┬─ human_review → report_writer_agent
                   └──────────────→ report_writer_agent
  → final_summary → END

Any node → error_handler on a critical error
error_handler → report_writer (recoverable) | final_summary (fatal)
```

Cross-cutting state fields (`warnings`, `errors`, `execution_log`) use
`Annotated[list, operator.add]` reducers, so every node simply returns the new
items it produced and LangGraph appends them.

---

## Installation

Python **3.11+** is required.

```bash
# from the repository root
python -m venv .venv && source .venv/bin/activate
pip install -e .

# optional: nicer logs + test deps
pip install -e ".[dev]"
```

Core dependencies: `langgraph`, `pydantic`, `pandas`, `PyYAML`, `typer`
(`rich` is optional).

---

## Quick start (dry-run prototype)

```bash
# 1. Inspect / describe the workflow graph
metamavs graph --config configs/example_config.yaml
metamavs graph --mermaid          # also print a Mermaid diagram

# 2. Validate config + manifest only
metamavs validate --config configs/example_config.yaml

# 3. Run the full workflow in dry-run mode
metamavs run --config configs/example_config.yaml --dry-run
```

(If you have not installed the package, prefix commands with
`python -m metamavs.cli`, e.g. `python -m metamavs.cli run --config ... --dry-run`.)

### What a run produces

Every run creates a self-contained run directory (default
`reports/example_run/`):

```text
reports/example_run/
  logs/            # metamavs.log, error_summary.json, final_summary.json
  intermediate/    # validated manifest, per-step JSON summaries
  commands/        # generated *.sh command scripts (FastQC, Kraken2, ...)
  tables/          # raw_viral_hits.csv, candidate_viral_taxa.csv,
                   # cleaned_taxonomy_table.csv, abundance_table.csv,
                   # trend_summary.csv, risk_table.csv, novel_candidate_table.csv
  report.md        # final Markdown surveillance report
  report.html      # final HTML report
  state.json       # complete final graph state
```

The example config ships a synthetic catalogue that includes **SARS-CoV-2**
(a configured high-risk pathogen), an environmental **phage**, a
**low-confidence** hit, and an **unclassified divergent** signal — so a dry run
exercises false-positive flagging, high-risk escalation, novel-candidate
detection, and the human-review branch end-to-end.

---

## Configuration

See [`configs/example_config.yaml`](configs/example_config.yaml). Key sections:
`project`, `input`, `execution` (`dry_run`, `mode`, `threads`), `tools`
(`qc`, `host_removal`, `viral_detection`, `assembly`, `novel_virus_screening`),
`risk` (high-risk pathogen list + review triggers), and `report` (formats).

## Manifest

See [`data/example_manifest.csv`](data/example_manifest.csv). Columns:
`sample_id, read1, read2, collection_date, location, sample_type`.
Validation rules: unique `sample_id`; `read1` required; `read2` required for
paired-end; `collection_date` parseable as `YYYY-MM-DD`; FASTQ paths may be
absent in dry-run but must exist in execution mode.

---

## Testing

```bash
pytest
```

Covers config loading, state/reducers, routing logic, manifest validation,
graph compilation, and a full end-to-end dry run.

---

## Project layout

```text
metamavs/
  cli.py            # Typer CLI (run / graph / validate / slurm)
  config.py         # pydantic config models + YAML loader
  schemas.py        # manifest schema + validation
  state.py          # MetaMAVSState (TypedDict + reducers)
  routing.py        # conditional routing functions
  graph.py          # StateGraph construction + compilation
  agents/           # one module per node
  utils/            # logging, files, command runner, taxonomy, report
  workflows/        # local (active) + slurm (placeholder) backends
```

---

## Roadmap

- **Phase 1 (this release):** deterministic dry-run prototype, full graph,
  reports, tests. ✅
- **Phase 2:** real subprocess execution, tool-availability checks, exit-code
  validation, SLURM job submission.
- **Phase 3:** wire in real bioinformatics tools (FastQC, fastp, Kraken2,
  DIAMOND, MEGAHIT, VirSorter2, CheckV, geNomad, …).
- **Phase 4:** optional LLM reasoning inside selected nodes (taxonomy
  interpretation, false-positive explanation, risk narrative, report prose).
  No LLM API key is required for Phases 1–3.

---

## License

MIT.
