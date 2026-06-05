# MetaMAVS

**MetaMAVS: Metagenomic Multi-Agent Virus Surveillance System**

A research-grade, **LangGraph-based** multi-agent workflow for viral
surveillance from wastewater, environmental, or clinical metagenomic sequencing
data. It runs end-to-end as a stateful `StateGraph`: input validation → QC →
host removal → viral detection → taxonomy → abundance → novel-virus screening →
risk assessment → human review → reporting.

All four development phases are complete: **deterministic local prototype
(Phase 1) → real command execution + SLURM (Phase 2) → hybrid local-control +
HPC-execution (Phase 3) → optional LLM agents (Phase 4)**. It runs fully
**deterministically and key-free** by default, with optional LLM reasoning and
NCBI grounding layered on top.

> ⚠️ **Scientific caution.** MetaMAVS reports *detected sequence signals*, not
> confirmed infections. High-risk detections always require confirmatory
> testing. Every layer (deterministic rules, LLM agents, reports) is designed to
> avoid over-claiming from weak metagenomic evidence.

See [`GUIDE_LINE.md`](GUIDE_LINE.md) / [`GUIDE_LINE_EN.md`](GUIDE_LINE_EN.md) for
the full design, and [`PHASE3_DESIGN.md`](PHASE3_DESIGN.md) for the hybrid-HPC
architecture.

---

## Why LangGraph?

MetaMAVS is **not** a collection of independent Python classes. The workflow is a
stateful [`StateGraph`](https://langchain-ai.github.io/langgraph/): each step is
a node that receives the shared state and returns a partial update. This gives
conditional routing, a human-in-the-loop checkpoint, checkpointing, error
diversion, and clean seams where LLM reasoning plugs in.

```text
START → input_manager → qc_agent → host_removal_agent → viral_detection_agent
  → [mode_router]
        ├─ hpc:  remote_execution → result_sync → tool_output_parser → taxonomy_agent
        └─ local/dry-run:                                            → taxonomy_agent
  → abundance_agent → novel_virus_agent → risk_assessment_agent
  → [review?] human_review → [pause?] (await `metamavs review`)
  → llm_interpretation → report_writer_agent → final_summary → END

Any node → error_handler on a critical error
```

Cross-cutting state fields (`warnings`, `errors`, `execution_log`, …) use
`Annotated[list, operator.add]` reducers, so every node returns only its new
items and LangGraph appends them.

---

## Installation

Python **3.11+** is required.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .            # core (deterministic, key-free)
pip install -e ".[dev]"     # + pytest, rich
pip install -e ".[llm]"     # + anthropic, python-dotenv (for the LLM agents)
```

Core deps: `langgraph`, `pydantic`, `pandas`, `PyYAML`, `typer`. Optional:
`rich`, `anthropic`, `python-dotenv`.

---

## Quick start (local, key-free)

```bash
metamavs graph    --config configs/example_config.yaml   # describe the workflow
metamavs validate --config configs/example_config.yaml   # validate config + manifest
metamavs tools    --config configs/example_config.yaml   # check tool availability
metamavs run      --config configs/example_config.yaml --dry-run   # full dry run
pytest                                                   # 119 tests
```

(Not installed? Prefix with `python -m metamavs.cli`.)

The example config ships a deterministic synthetic catalogue (SARS-CoV-2, a
phage, a low-confidence hit, an unclassified divergent signal) so a dry run
exercises false-positive flagging, high-risk escalation, novel-candidate
detection, and the review branch end-to-end.

### What a run produces

```text
reports/<run_name>/
  report.md / report.html   # final surveillance report
  state.json                # complete final graph state
  tables/                   # raw_viral_hits, candidate/cleaned taxonomy,
                            # abundance, trend, risk, novel candidate (CSV)
  intermediate/  commands/  logs/   # summaries, generated *.sh, logs
  remote/  results/raw/     # (HPC mode) job ledger, scripts, downloaded outputs
```

---

## LLM agents (optional, Phase 4)

Six nodes are **real LLM agents** (Anthropic Claude) when enabled; otherwise they
fall back to deterministic logic:

| Node | LLM role |
|---|---|
| `qc_agent` | data-adequacy assessment |
| `taxonomy_agent` | phage / pathogen / false-positive classification (NCBI-grounded) |
| `abundance_agent` | epidemiological trend interpretation |
| `novel_virus_agent` | novel/divergent candidate assessment |
| `risk_assessment_agent` | per-taxon risk + reasoning (NCBI-grounded) |
| `llm_interpretation` | public-health surveillance narrative |

Four guarantees for every LLM agent:

1. **Optional & key-free fallback** — off by default; missing key / SDK / API
   failure → deterministic behaviour. Phases 1–3 never need a key.
2. **Grounded, not memory-only** — judgement is grounded in verified **NCBI
   Taxonomy** lineage (queried by taxid; `Division: Phages` = authoritative
   phage), a curated **literature reference**, and per-pathogen snippets.
3. **Deterministic safety rails** — the LLM may only *add* caution: phages and
   false positives pinned Low, configured high-risk pathogens floored at High;
   PMMoV / crAssphage treated as normalization **controls**, not threats.
4. **Prompt caching** — the shared reference is the cached system-prompt prefix
   (cross-agent cache hits within a run).

Enable it:

```bash
echo 'ANTHROPIC_API_KEY=sk-ant-...' > .env       # .env is gitignored
```
```yaml
# in your config
llm:  { enabled: true, model: claude-opus-4-8, effort: medium }
ncbi: { enabled: true, email: you@example.com }   # verified NCBI lineage grounding
```

---

## Human-in-the-loop review

The review checkpoint triggers on High/Critical risk, novel candidates, or QC
failure. `human_review.mode`:

- **auto** (default) — simulate approval (non-blocking automation).
- **interactive** — y/N prompt at a real TTY.
- **pause** — pause the run and exit, persisting a resumable snapshot; a human
  later approves/rejects and resumes:

```yaml
human_review: { mode: pause }
```
```bash
metamavs run    --config configs/sapelo2_config.yaml --execute   # runs, then PAUSES
metamavs review --run-dir reports/<run_name>                     # shows context, prompts
metamavs review --run-dir reports/<run_name> --approve --notes "…"   # or non-interactive
```

Approval resumes interpretation → report → final; rejection finalizes with no
report. The decision and reviewer notes are recorded in the report. Decoupled
from the run, so it works with background / long HPC runs and delayed decisions.

---

## HPC (Phase 3): local control + HPC execution

`execution.mode: hpc` submits the bioinformatics steps to a remote SLURM cluster
while orchestration, parsing and reporting stay local. SSH ControlMaster reuses
one authentication (e.g. GACRC Duo) for the whole run; only self-contained SLURM
scripts cross to the cluster; results are downloaded and parsed locally.

```bash
metamavs remote-check --config configs/sapelo2_config.yaml   # diagnose ssh/sbatch/paths
metamavs run          --config configs/sapelo2_config.yaml --execute
```

See [`configs/sapelo2_config.yaml`](configs/sapelo2_config.yaml) (a real UGA
GACRC Sapelo2 example) and [`PHASE3_DESIGN.md`](PHASE3_DESIGN.md). Local testing
uses a `MockBackend` + fixtures — no cluster needed.

---

## Configuration & manifest

- **Config** — [`configs/example_config.yaml`](configs/example_config.yaml):
  `project`, `input`, `execution`, `tools`, `risk`, `report`, plus optional
  `hpc`, `llm`, `ncbi`, `human_review`. Config = "how to run"; manifest = "what
  to run on".
- **Manifest** — [`data/example_manifest.csv`](data/example_manifest.csv):
  `sample_id, read1, read2, collection_date, location, sample_type`. Unique
  `sample_id`; `read1` required; `read2` for paired-end; dates `YYYY-MM-DD`.
  `input.remote_data: true` means read1/read2 are paths already on the HPC.

---

## Project layout

```text
metamavs/
  cli.py            # Typer CLI (run / graph / validate / tools / remote-check / review / slurm)
  config.py state.py schemas.py routing.py graph.py
  pathogens.py      # high-risk pathogen matching (taxid + aliases)
  controls.py       # PMMoV / crAssphage normalization controls
  taxonomy_db.py    # NCBI Taxonomy lookup (verified lineage)
  agents/           # one module per node
  parsers/          # FastQC, flagstat, Kraken2, Bracken, GOTTCHA2, DIAMOND, CheckV
  remote/           # RemoteBackend (SSH/Mock), SLURM, job ledger, job DAG
  llm/              # client (Claude), prompts, reference (literature grounding)
  utils/  workflows/  # logging/files/exec; local + slurm backends
```

---

## Roadmap

- **Phase 1** — deterministic local dry-run prototype. ✅
- **Phase 2** — real subprocess execution, tool checks, validation, SLURM. ✅
- **Phase 3** — hybrid local-control + HPC-execution (verified on UGA Sapelo2
  with real GOTTCHA2). ✅
- **Phase 4** — optional LLM agents (6), NCBI + literature grounding,
  pause/resume human review. ✅ *(no API key required for Phases 1–3)*

Possible next: multi-timepoint trend analysis, more bioinformatics tools per
step, richer literature retrieval.

---

## License

MIT.
