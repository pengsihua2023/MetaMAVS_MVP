# MetaMAVS Overall Design Guide

> This document explains three things:
> 1. What MetaMAVS is and why it is designed this way;
> 2. The **4 development phases**, what each does, and where we currently stand;
> 3. How the technical framework is layered and what role each file/library plays.
>
> Companion reading: `README.md` (installation & usage), `CLAUDE.md` (the
> specification written for AI collaborators), `GUIDE_LINE.md` (Chinese version).

---

## 1. One-Line Definition

**MetaMAVS = Metagenomic Multi-Agent Virus Surveillance System**
A **LangGraph**-based, stateful **multi-agent workflow system** for viral
surveillance from **wastewater / environmental / clinical metagenomic
sequencing data**: QC → host removal → viral detection → taxonomy → abundance
trends → novel virus screening → risk assessment → human review → automated
reporting.

Three keywords that define it:
- **Research-grade**: scientifically cautious, never overstating weak signals.
- **Multi-agent**: not a sequential script, but a LangGraph state machine.
- **Evolvable (LLM-ready)**: the first version is fully deterministic; LLM
  reasoning can later be injected into individual nodes.

---

## 2. Core Design Philosophy (Why It Is Built This Way)

### 2.1 A LangGraph state machine, not a sequential script
The project **requires** the core workflow to be expressed as a LangGraph
`StateGraph`. Reasons:

- **Conditional routing**: the flow must "turn" toward human review on high
  risk / novel candidates / QC failure, rather than marching straight ahead.
- **Error diversion**: any node hitting a critical error can route to
  `error_handler` instead of crashing the whole run.
- **Human-in-the-loop (HITL)**: pause at key decision points for a human.
- **Checkpointing**: recoverable and traceable.
- **Testability**: each node is an independent pure function, testable alone.

### 2.2 One shared state flows through everything
All data lives in a single `MetaMAVSState` (a `TypedDict`). Each node receives
the full state and returns only a **partial update** (a partial dict), which
LangGraph merges back in.
The `warnings` / `errors` / `execution_log` fields use
`Annotated[list, operator.add]` **reducers**, so every node only returns the
"new few items" it produced and the framework appends them automatically —
no accidental overwrites.

### 2.3 Framework dependency centralized in one file
Only `graph.py` imports LangGraph directly. The 12 agents and the routing
functions are plain Python functions → testable without the framework, and
future upgrades/replacements stay cheap.

### 2.4 Separation of concerns by layer
- **Orchestration layer** (framework): LangGraph, decides "how the flow goes".
- **Node layer** (business): 12 agents, each does one analysis step.
- **Utility layer** (infrastructure): logging / files / command building /
  taxonomy / report rendering.
- **Data validation layer** (a tool library): pydantic only checks whether the
  config and manifest are valid — it is **not** an orchestration framework.

### 2.5 Scientific caution is a hard constraint
Reports say "detected sequence signal" rather than "confirmed infection";
phages are reported separately from human pathogens; low read counts, low
complexity, and possible contamination are flagged; high-risk detections must
recommend confirmatory testing. This runs through the `taxonomy` / `risk` /
`report` nodes.

---

## 3. How Many Phases? — 4 in Total

MetaMAVS uses **incremental delivery**: get the skeleton running first, then add
real capabilities step by step. There are **4 phases total**:

| Phase | Name | Goal | External tools needed? | LLM API key needed? | Status |
|---|---|---|---|---|---|
| **Phase 1** | Minimal Runnable Prototype | Deterministic, local, dry-run run of the full LangGraph flow, with reports + tests | ❌ No | ❌ No | ✅ **Done** |
| **Phase 2** | Real Command Execution | Actually execute the generated commands; tool checks, validation, recovery, SLURM | ⚠️ Some | ❌ No | ✅ **Done** |
| **Phase 3** | Bioinformatics Expansion (hybrid HPC) | Local controller submits SLURM jobs to a remote HPC, downloads results, parses them locally | ✅ Yes (on HPC) | ❌ No | ✅ **Done (v1)** |
| **Phase 4** | Intelligent Interpretation | Optional LLM (Claude) writes the surveillance narrative; deterministic risk stays authoritative | ✅ Yes | ✅ Yes (optional) | ✅ **Done** |

Each phase is detailed below.

### Phase 1 — Minimal Runnable Prototype ✅ (Done)
**What was built**
- Full project skeleton + YAML config loading + sample manifest validation
- `MetaMAVSState` definition + LangGraph graph construction/compilation
- Dry-run logic for all 12 nodes + command generation
- Intermediate artifacts persisted (CSV/JSON) + Markdown/HTML report
- CLI: `metamavs run --dry-run`, `metamavs graph`, `validate`, `slurm`
- 37 pytest tests, all green

**Key trait**: executes no external commands, no network, no database, no root,
no API key. In dry-run mode it uses **deterministic synthetic data** so the
entire flow (including high-risk escalation, phage flagging, novel candidates,
and the human-review branch) is exercised end-to-end.

**Definition of Done** — all satisfied:
- `metamavs run --config configs/example_config.yaml --dry-run` runs successfully
- The LangGraph graph compiles; 12 nodes execute in order; conditional review
  routing works
- Intermediate files are generated; the final Markdown report is generated
- config/state/graph/routing/manifest tests pass; README is complete

### Phase 2 — Real Command Execution ✅ (Done)
Delivered on top of Phase 1 without touching the graph wiring:
- **Real command execution** via subprocess with a retry loop
  (`CommandRunner.run` + `utils/execution.py`)
- **Tool-availability checks** (`shutil.which`) + a new `metamavs tools` command
- **Exit-code validation** with **warn-and-continue** recovery; configurable
  `execution.retries`
- **Output-file validation** (expected outputs checked after execution)
- **Graceful fallback**: when a required tool is missing, the step warns and
  falls back to synthetic data so the pipeline still completes
- Per-step execution logs (`logs/exec_<step>.log`) and an `execution_reports`
  state accumulator
- **SLURM script generation** driven by a config `slurm:` section
  (`workflows/slurm_workflow.py`)
- 13 new tests (50 total, all passing); dry-run behavior fully preserved

### Phase 3 — Bioinformatics Expansion (hybrid HPC) ✅ (v1 done)
Hybrid **local-control + HPC-execution + result-repatriation** architecture (see
`PHASE3_DESIGN.md`). MetaMAVS stays local; only self-contained SLURM scripts +
inputs cross to the cluster; results are downloaded and parsed locally.
- `metamavs/remote/`: `RemoteBackend` abstraction (`SSHBackend` real,
  `MockBackend` for local testing), `slurm.py` (script gen, `sacct` parsing,
  dependency DAG, polling), `job_ledger.py` (resumable jobs.json), `jobgen.py`.
- 3 new agents: `remote_execution` (stage→sbatch DAG→monitor), `result_sync`
  (download + integrity), `tool_output_parser` (raw outputs → normalized tables).
- `metamavs/parsers/`: FastQC, samtools flagstat, Kraken2, Bracken, DIAMOND,
  CheckV — defensive parsers feeding the existing taxonomy/abundance/risk agents.
- New `execution.mode: hpc` + `hpc:` config; `input.remote_data` for data already
  on the cluster; `mode_router` selects local vs remote without touching Phase 1/2.
- 17 new tests incl. a full hpc-mode integration run via `MockBackend` + fixtures
  (no real cluster). 67 tests total, all passing.

**Real-cluster hardening (UGA GACRC Sapelo2):**
- SSH ControlMaster multiplexing so Duo 2FA is entered **once** per run;
  `metamavs remote-check` diagnoses ssh/scheduler/paths/conda-env before running.
- conda-env execution (`env_setup` + `conda activate`) instead of modules;
  GOTTCHA2 command generator + parser added alongside Kraken2/Bracken.
- `configs/sapelo2_config.yaml` (host/user/partition `bahl_p`/remote_base/conda
  env prefilled; DB paths marked TODO). 72 tests total, all passing.
- Remaining (user-side, needs the cluster): fill DB/host-ref/manifest paths,
  confirm the conda module name, then run `remote-check` and a small live smoke run.

### Phase 4 — Intelligent Interpretation (LLM) ✅ (Done)
An **optional** LLM interpretation layer (Anthropic Claude), fully additive:
- `metamavs/llm/` — defensive client (loads `.env` with `override=True`,
  `claude-opus-4-8` + adaptive thinking, cache_control breakpoint on a static
  cautious system prompt; any failure → `None`) + per-run user-prompt builder.
- New `llm_interpretation` node between risk/human-review and the report writer;
  writes an advisory "AI-Assisted Interpretation" section (Executive Summary,
  Risk Interpretation, Recommended Actions, Caveats). The **deterministic risk
  assessment stays authoritative**.
- `LLMConfig` (`enabled` off by default, `model`/`effort`/`max_tokens`); `[llm]`
  extra (`anthropic`, `python-dotenv`); `.env` gitignored.
- **Graceful fallback**: no key / `enabled=false` / SDK or API failure → clean
  no-op; Phases 1–3 remain key-free. 6 new tests (90 total).
- Live-verified with a real key: Claude produced a scientifically-cautious
  narrative (detected-signal framing, per-pathogen RT-qPCR confirmation, phages
  separated, explicit caveats).

> Caching note: the static system prompt (~541 tokens) is below Anthropic's
> ~1024-token cache minimum, so the breakpoint is a no-op at this size — placed
> correctly, it auto-engages when the cached prefix grows (e.g. literature
> context). Future work: taxonomy/false-positive interpretation, literature-aware
> pathogen context, public-health alert summarization.

**Principle**: even at Phase 4, Phases 1–3 keep "runnable without an API key";
the LLM is an optional enhancement, not a hard dependency.

### Phase Evolution Diagram
```
Phase 1 (✅ deterministic dry-run)
   │  wire CommandRunner.run to subprocess
   ▼
Phase 2 (real execution + SLURM + recovery)
   │  parse each tool's report into the unified data structure
   ▼
Phase 3 (all real bioinformatics tools integrated)
   │  insert LLM reasoning inside nodes (optional)
   ▼
Phase 4 (LLM intelligent interpretation)
```
**Key point: after each phase the system stays runnable, and the next phase does
not require rewriting the previous one.**

---

## 4. Technical Framework and Layering

### 4.1 Framework layering diagram
```
┌────────────────────────────────────────────────────────┐
│  Orchestration / Framework   LangGraph (StateGraph)     │  graph.py is the only contact
│  nodes, conditional edges, checkpoint, HITL, error route │
└────────────────────────────────────────────────────────┘
        ▲ assembles and drives the 12 nodes
┌────────────────────────────────────────────────────────┐
│  Node / Business   agents/*.py (12 agents)              │  pure functions (state)->dict
└────────────────────────────────────────────────────────┘
        ▲ calls
┌────────────────────────────────────────────────────────┐
│  Utility / Infrastructure  utils/*.py                    │  logging/files/command/taxonomy/report
│  Data validation  config.py + schemas.py (pydantic)     │  validates data legality only
└────────────────────────────────────────────────────────┘
```

### 4.2 Role of each dependency (to avoid confusion)
| Library | Category | What it does in the project |
|---|---|---|
| **LangGraph** | **Multi-agent / workflow framework** (the only core framework) | StateGraph, nodes, conditional routing, checkpoint |
| pydantic | Data validation library (a tool) | Validates config and manifest; **not** an orchestration framework |
| pandas | Data processing library | Reads/writes CSV, aggregates tables |
| PyYAML | Parsing library | Reads YAML config |
| typer | CLI library | Command-line entry point |
| pytest | Testing framework | Unit / end-to-end tests |
| (LangChain) | Possibly introduced only in Phase 4 | LLM messages/wrappers; currently **unused** |

> Note: only **LangGraph** is a "multi-agent programming framework"; pydantic and
> the others are plain tool libraries driven by it. They form a "framework +
> tools" layered collaboration, not a "mix of two frameworks".

---

## 5. Shared State `MetaMAVSState`

Defined in `state.py` as a `TypedDict(total=False)`. Design points:

- **Most fields**: last-write-wins (LangGraph's default behavior).
- **Three accumulator fields** `warnings` / `errors` / `execution_log`: use
  `Annotated[list, operator.add]`; each node returns only new items, appended
  automatically.
- `create_initial_state(...)` initializes every field with sensible defaults.

Field groups: run metadata → input → per-node products
(qc/host/detection/taxonomy/abundance/novel/risk) → human review → report paths
→ cross-cutting accumulators → workflow status.

---

## 6. Workflow Structure (12 Nodes)

### 6.1 Main flow
```
START
  → input_manager            (1) validate input, produce clean manifest
  → qc_agent                 (2) QC commands + pass/fail decision
  → host_removal_agent       (3) host-removal commands + non-host reads
  → viral_detection_agent    (4) detection commands + hit tables
  → taxonomy_agent           (5) taxonomy cleanup + false-positive/phage flags
  → abundance_agent          (6) RPM normalization + trends
  → novel_virus_agent        (7) assembly/screening commands + novel candidates
  → risk_assessment_agent    (8) four-level risk grading + review decision
  → [conditional_review_router]
        ├─ human_review       (9) human-in-the-loop review (when needed)
        └─────────────────────→ report_writer (straight through if not needed)
  → report_writer_agent      (10) Markdown + HTML report
  → final_summary            (11) final summary + state.json
  → END

Any node with a critical error → error_handler (12) → best-effort report if it can continue, else finalize
```

### 6.2 Node responsibility quick reference
`🧠` marks nodes that are **LLM agents** (use Claude when enabled; deterministic
fallback otherwise). The Phase 3 remote nodes (remote_execution, result_sync,
tool_output_parser) and llm_interpretation are omitted here for brevity.

| # | Node | LLM | One-line responsibility |
|---|---|---|---|
| 1 | input_manager | | Entry gatekeeper: validate manifest/metadata, produce `validated_manifest.csv` |
| 2 | qc_agent | 🧠 | QC commands + pass/fail; LLM data-adequacy assessment |
| 3 | host_removal_agent | | Generate Bowtie2/BWA/minimap2 host-removal commands |
| 4 | viral_detection_agent | | Generate Kraken2/DIAMOND/GOTTCHA2 commands, produce raw hits + candidate taxa |
| 5 | taxonomy_agent | 🧠 | Normalize taxonomy; LLM classifies phage/pathogen/false-positive, **grounded in NCBI lineage** |
| 6 | abundance_agent | 🧠 | RPM normalization + trends; LLM epidemiological trend interpretation |
| 7 | novel_virus_agent | 🧠 | Assembly + screening commands; LLM assesses novel/divergent candidates |
| 8 | risk_assessment_agent | 🧠 | Low/Medium/High/Critical per taxon; LLM reasoning + NCBI lineage, within safety rails |
| 9 | human_review | | HITL checkpoint (auto / interactive / **pause-and-resume**) |
| (–) | llm_interpretation | 🧠 | Public-health surveillance narrative for the report |
| 10 | report_writer_agent | | Generate Markdown + HTML surveillance report |
| 11 | final_summary | | Final summary, report paths, persist `state.json` |
| 12 | error_handler | | Classify errors, decide whether to continue, prevent silent failures |

### 6.3 LLM agents (the "brains")
Six nodes are **real LLM agents** (Anthropic Claude, `claude-opus-4-8`): qc,
taxonomy, abundance, novel_virus, risk, and llm_interpretation. The other nodes
are infrastructure / IO / control and deliberately stay deterministic — they
don't need a brain.

**Design principles (all four hold for every LLM agent):**
1. **Optional & key-free fallback** — disabled by default (`llm.enabled: false`);
   no key / SDK / API failure → clean fall back to deterministic logic. Phases
   1–3 never need an API key.
2. **Grounded, not memory-only** — judgement is grounded in (a) verified **NCBI
   Taxonomy** lineage fetched by taxid (`ncbi.enabled`, local controller; Division
   `Phages` = authoritative phage), (b) a curated **literature reference**
   (`llm/reference.py`, also the cached prefix), and (c) per-pathogen snippets.
3. **Deterministic safety rails** — the LLM may only *add* caution, never reduce
   it: phages/false-positives pinned Low, configured high-risk pathogens floored
   at High (`_clamp_llm_risk`); taxonomy flags are a union (LLM can add, not
   remove); PMMoV/crAssphage treated as normalization **controls**, not threats.
4. **Cost-aware** — the shared reference is the cached system-prompt prefix
   (>1024 tokens → real prompt-cache hits across agents within a run).

Knowledge layers stacked per judgement: **NCBI (authoritative) + literature
reference + Claude training knowledge → inside deterministic safety rails.**

### 6.4 Human-in-the-loop review (`human_review.mode`)
The review checkpoint can genuinely involve a human. Triggered when overall risk
is High/Critical, novel candidates exist, or a sample fails QC. Three modes:
- **auto** (default): simulate approval — non-blocking, for automation/CI.
- **interactive**: y/N prompt at a real TTY (foreground runs).
- **pause**: PAUSE the run at the checkpoint and exit, persisting a resumable
  snapshot (`paused_state.json`) + `review_request.json`. A human later runs
  `metamavs review --run-dir <dir>` to see the risk context and approve/reject
  (`--approve`/`--reject` or interactive). Approval resumes
  interpretation→report→final; rejection finalizes with no report. Decoupled
  from the run, so it works with **background / long HPC runs and delayed human
  decisions** — the decision and reviewer notes are recorded in the report.

### 6.5 Routing logic (`routing.py`)
- `make_step_router(next)`: the "error guard" attached after each backbone node
  — on a critical error route to `error_handler`, otherwise to the next node.
- `mode_router`: after viral_detection — to the remote (HPC) chain if
  `execution.mode == hpc`, else straight to taxonomy.
- `review_router`: branch after risk — to `human_review` if review needed,
  otherwise to `llm_interpretation` → report.
- `review_pause_router`: after `human_review` — to END if the run paused for a
  human (resume later via `metamavs review`), else continue to interpretation.
- `error_handler_router`: after `error_handler` — to `report_writer` if it can
  continue, otherwise to `final_summary`.
- `should_request_review`: decides whether to trigger human review (high/critical
  risk, novel candidates, QC failure).

---

## 7. Directory Structure and File Responsibilities

```text
MetaMAVS/
  GUIDE_LINE.md          # Overall design guide (Chinese)
  GUIDE_LINE_EN.md       # Overall design guide (English, this file)
  README.md              # Installation & usage
  CLAUDE.md              # Specification for AI collaborators
  pyproject.toml         # Dependencies & CLI entry point
  configs/
    example_config.yaml  # Example config
  data/
    example_manifest.csv # Example sample manifest
  metamavs/
    __init__.py          # Version
    cli.py               # Typer CLI: run / graph / validate / slurm
    config.py            # pydantic config models + YAML loading
    schemas.py           # Manifest schema + validation rules
    state.py             # MetaMAVSState (TypedDict + reducers)
    routing.py           # Conditional routing functions
    graph.py             # ★Only contact with LangGraph: build+compile StateGraph
    agents/              # 12 nodes, one file each
    utils/               # logging / file / command_runner / taxonomy / report
    workflows/
      local_workflow.py  # Local execution backend (active)
      slurm_workflow.py  # SLURM backend (Phase 2 placeholder)
  reports/               # Run artifacts (example report committed; large files .gitignored)
  tests/                 # config/state/graph/routing/manifest tests
```

### Directory produced by each run
```text
reports/<run_name>/
  logs/          # metamavs.log, error_summary.json, final_summary.json
  intermediate/  # validated manifest + per-step JSON summaries
  commands/      # generated *.sh command scripts
  tables/        # various CSV result tables
  report.md      # final Markdown report
  report.html    # final HTML report
  state.json     # complete final state
```

---

## 8. How to Run (Quick Recap)

```bash
pip install -e ".[dev]"
metamavs graph    --config configs/example_config.yaml   # view workflow structure
metamavs validate --config configs/example_config.yaml   # validate config + manifest
metamavs tools    --config configs/example_config.yaml   # check tool availability
metamavs run      --config configs/example_config.yaml --dry-run  # run full flow
# HPC (Phase 3): real run + human-in-the-loop review
metamavs remote-check --config configs/sapelo2_config.yaml        # diagnose SSH/SLURM
metamavs run          --config configs/sapelo2_config.yaml --execute  # may PAUSE for review
metamavs review --run-dir reports/<run_name> --approve --notes "…"   # human decision
pytest                                                    # run tests
```
(If not installed, use `python -m metamavs.cli ...` instead of `metamavs`.)

**Optional LLM + NCBI grounding:** put `ANTHROPIC_API_KEY` in `.env`, set
`llm.enabled: true` and (optionally) `ncbi.enabled: true` in the config. Without
these, everything runs deterministically and key-free.

---

## 9. Advice for Future Developers (Moving Beyond Phase 1)

1. **Do not rewrite**: each phase is an incremental extension of the previous one.
2. **Phase 2 entry point**: `CommandRunner.run` in `utils/command_runner.py`
   already reserves a real-execution branch; wire subprocess there first, then
   extend `error_handler` for retry/skip.
3. **Phase 3 entry point**: write one "report parser" per tool that converts real
   output into the existing `raw_viral_hits` / taxonomy table structure;
   **downstream nodes need no changes**.
4. **Phase 4 entry point**: insert LLM calls inside nodes such as `taxonomy` /
   `risk` / `report`; keep the LLM optional so no-key runs still work.
5. **Keep discipline**: nodes stay pure functions `(state)->dict`; framework
   dependency stays only in `graph.py`; keep scientific language cautious; run
   `pytest` after changes.

---

## 10. One-Page Summary

- **What it is**: a LangGraph-based multi-agent virus surveillance workflow.
- **How many phases**: **4**. Phase 1 (deterministic prototype, ✅ done) →
  Phase 2 (real execution + SLURM) → Phase 3 (real bioinformatics tools) →
  Phase 4 (LLM interpretation).
- **Core framework**: **LangGraph only**; pydantic/pandas/typer etc. are tool
  libraries, not a second framework.
- **Architectural essence**: shared state + 12 pure-function nodes + conditional
  routing + error diversion + human-in-the-loop; framework dependency confined
  to a single file; scientific caution throughout; clean seams reserved for LLM
  evolution.
