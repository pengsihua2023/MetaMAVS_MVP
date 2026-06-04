# MetaMAVS Phase 3 Design — Hybrid Local-Control + HPC-Execution

> **Goal:** real bioinformatics tool execution on a remote SLURM HPC cluster,
> while MetaMAVS itself (LangGraph orchestration, parsing, reporting) keeps
> running **locally**. Pattern: **local controller → HPC executor → results
> repatriated → parsed locally**.
>
> This document answers the 10 design questions, then gives the recommended
> architecture, data structures, LangGraph flow, error handling, local testing
> strategy, a phased implementation checklist, and key code skeletons.

---

## 0. TL;DR recommendation

- **Do NOT copy MetaMAVS to the HPC.** The only artifacts that cross to the
  cluster are **self-contained SLURM bash scripts + input files**. The HPC needs
  the *tools* (modules/conda) — not the MetaMAVS Python package. Parsing and
  reporting happen **locally** after results are downloaded.
- **Three new agents**, not two: `remote_execution` (lifecycle: stage→submit→
  monitor), `result_sync` (download + integrity), `tool_output_parser`
  (raw outputs → normalized tables). Parsing is split out because it is pure,
  local, reusable and where Phase 3's real value (correct parsing) lives.
- **One key abstraction makes everything testable: `RemoteBackend`** with
  `SSHBackend` (real) and `MockBackend` (local fake HPC). The entire pipeline
  is testable with zero cluster access.
- **Communication:** subprocess `ssh` + `rsync` (respects `~/.ssh/config`,
  ProxyJump, keys; rsync gives checksummed, resumable transfer) + SLURM
  `sbatch`/`sacct`. A durable **job ledger** (`jobs.json`) makes runs resumable
  across controller restarts (HPC jobs run for hours).
- **Reuse Phase 1/2 philosophy:** dry-run preserved, graceful degradation,
  warn-and-continue, framework dependency confined to `graph.py`, additive (no
  rewrite of earlier phases).

---

## 1. Should the code be copied to HPC?

**No — keep MetaMAVS local. Deploy only scripts + inputs to a lightweight remote
working directory.**

| Component | Where | Why |
|---|---|---|
| MetaMAVS package, LangGraph graph, routing | **Local** | The "brain"; orchestration/decisions don't need HPC compute |
| Output parsers, taxonomy/abundance/risk logic, report writer | **Local** | Pure, CPU-light; need no cluster; easiest to develop/test locally |
| Generated **SLURM bash scripts** (self-contained: `module load` + tool cmds) | **HPC** | The only code that must run on the cluster |
| Input FASTQ + databases | **HPC** | Big; often already on cluster scratch; uploaded or referenced in place |
| Bioinformatics tools (FastQC, Kraken2, DIAMOND, VirSorter2…) | **HPC** | Already installed via modules/conda — MetaMAVS just calls them |

**Lightweight remote work dir: yes.** Per-run directory holding inputs, scripts,
logs, results (layout in §4). **No MetaMAVS Python install on HPC** — avoids env
management, version drift, internet-less login-node pain. The SLURM script is
plain bash; the cluster never imports MetaMAVS.

> Why not run the whole pipeline on HPC? Login nodes kill long-running
> orchestrators, have no/limited internet, and module/conda conflicts make a
> Python+LangGraph env fragile. Parsing/reporting gain nothing from HPC compute.
> See §10.

---

## 2. Agent design — 3 agents, strict boundaries

Recommended decomposition (refines your `HPCExecutionAgent` + `ResultSyncAgent`):

| Agent | Owns | Does NOT do | Failure modes |
|---|---|---|---|
| **remote_execution_agent** | Remote **job lifecycle**: stage/upload inputs+scripts, `sbatch` (as a dependency DAG), poll `sacct` until all jobs reach a terminal state | Download result files; parse | SSH connect, upload, sbatch, job FAILED/TIMEOUT/OOM |
| **result_sync_agent** | **Data transfer** HPC→local + **integrity** (size/checksum), organize `results/raw/` | Submit jobs; parse | partial/incomplete download, missing outputs |
| **tool_output_parser_agent** | Parse **local** raw files → **normalized tables** (same schema downstream agents already consume) | Any SSH/SLURM | malformed/unexpected tool output |

**Why 3, not 2:** parsing is pure-local, reusable (works for HPC *or* a future
local-exec run), and is the single highest-value, most testable unit in Phase 3.
Merging it into sync would entangle I/O with format logic. **Why not split
submit vs monitor:** they share the SSH/job context; a separate `JobMonitorAgent`
would be a thin polling loop that just adds coordination overhead. (It *can*
later become a self-looping LangGraph node — see §5 note.)

**Overlap avoided by a hard contract:** `remote_execution` ends exactly when
"all jobs reached terminal state" (status known via `sacct`) and has **not**
downloaded anything. `result_sync` only moves bytes + verifies. `parser` only
reads local files. Each writes a distinct state slice (§6).

---

## 3. Local ↔ HPC communication

**Abstract everything behind a `RemoteBackend` interface** (this is what makes it
testable, §8). Concrete backends:

- **`SSHBackend` (default real):** subprocess `ssh` + `rsync`.
  - Transfer: **`rsync -avz --partial --checksum`** (resumable, integrity-checked) both
    directions; `scp` fallback.
  - Commands: `ssh <host> "<cmd>"` to run `sbatch`/`sacct`/`mkdir`.
  - Honors `~/.ssh/config` (Host alias, `ProxyJump` for bastion, IdentityFile,
    ControlMaster for connection reuse) — no credentials in MetaMAVS.
- **`MockBackend` (tests/dev):** fakes a remote dir on the local FS; "submit"
  drops pre-canned fixture outputs; "status" returns a scripted state sequence.

**SLURM interaction:**
- Submit: `sbatch --parsable script.sh` → returns job id; chain with
  `--dependency=afterok:<id>` to encode the QC→host→detection→assembly DAG.
- Status: **`sacct -j <id> --format=JobID,State,ExitCode --parsable2 --noheader`**
  (sacct reports terminal jobs that already left the queue; `squeue` only shows
  pending/running). Poll every `hpc.poll_interval_s`.

**Path & id management + state persistence:**
- A **`RemoteJobSpec`** (§6) carries local↔remote paths, expected outputs, deps.
- A durable **job ledger** `reports/<run>/remote/jobs.json` records
  `{job_name → {job_id, remote_paths, state, exit_code}}`. Persisted on every
  poll so a **restarted controller re-attaches to running jobs instead of
  resubmitting** (critical: HPC jobs run for hours).
- In-process state via LangGraph `MemorySaver`; durable cross-restart state via
  the JSON ledger (and optionally `langgraph.checkpoint.sqlite.SqliteSaver`).

---

## 4. Directory structure

**Local (per run):**
```text
reports/<run_name>/
  remote/
    jobs.json                 # durable job ledger (job_id ↔ paths ↔ state)
    staging/                  # files assembled locally before upload
    scripts/                  # generated SLURM scripts (uploaded copy of truth)
  results/
    raw/<tool>/<sample>/      # downloaded raw tool outputs (untouched)
  tables/                     # parsed, normalized tables (existing Phase 1 dir)
  logs/                       # controller logs, exec_<step>.log, slurm fetch logs
  report.md / report.html / state.json
```

**HPC remote (per run): `$HPC.remote_base/metamavs/<run_id>/`**
```text
inputs/      # uploaded FASTQ (or symlinks to existing cluster data)
scripts/     # SLURM scripts
work/        # tool scratch / assembly dirs
results/     # standardized outputs intended for download
logs/        # slurm_%j.out / slurm_%j.err
```

Convention: every tool writes its deliverables into `results/<tool>/<sample>/`
with fixed names, so `result_sync` knows exactly what to pull and `parser` knows
exactly what to read.

---

## 5. Recommended LangGraph workflow

Phase 3 **adds a mode** (`execution.mode: hpc`) and **3 nodes**, without
rewriting Phase 1/2. The existing command-builder agents become **mode-aware**:
in `hpc` mode they emit a `RemoteJobSpec` (build the SLURM script) instead of
executing locally; in `dry_run`/`local` mode they behave exactly as today.

```text
START
  → input_manager
  → qc_agent              ─┐  (in hpc mode each BUILDS a RemoteJobSpec +
  → host_removal_agent     │   SLURM script; in dry-run/local: unchanged)
  → viral_detection_agent  │
  → novel_virus_agent     ─┘
  → [route on execution.mode]
        ├─ hpc:  remote_execution_agent     # upload + sbatch DAG + monitor   [NEW]
        │        → result_sync_agent        # download + integrity verify     [NEW]
        │        → tool_output_parser_agent # raw outputs → normalized tables [NEW]
        └─ local/dry-run: (skip the 3 remote nodes; tables already produced)
  → taxonomy_agent         # now consume REAL parsed tables when in hpc mode
  → abundance_agent
  → risk_assessment_agent
  → conditional_review_router → human_review? → report_writer_agent
  → final_summary → END

Any node → error_handler on critical error (existing).
```

**Why batched remote stage (model B) over per-step remote (model A):** keeps the
existing 12-node structure and the command-builders' investment; centralizes all
SSH in one agent (one place to harden); maps stage dependencies to a single
SLURM `--dependency` DAG submitted once. (Model A — each agent submits/monitors
its own job — spreads SSH across 4 agents and multiplies failure surface.)

**Monitor-as-loop note:** v1 polls inside `remote_execution_agent` (blocking with
sleep). It is designed so monitoring can later be promoted to a self-looping
`job_monitor` node (conditional edge to itself until terminal) for non-blocking,
checkpoint-resumable waits — no other node changes required.

---

## 6. Key data structures (pydantic, in `metamavs/remote/types.py`)

```python
class ResourceSpec(BaseModel):
    partition: str = "batch"
    cpus: int = 8
    mem: str = "32G"
    time: str = "24:00:00"

class RemoteJobSpec(BaseModel):
    job_name: str                       # unique, e.g. "kraken2__sample_001"
    step: str                           # "qc" | "host_removal" | "viral_detection" | ...
    sample_id: str | None = None
    script_local: str                   # path to generated .sh (local)
    script_remote: str                  # path on HPC
    input_files: list[str] = []         # local paths to upload
    output_files: list[str] = []        # expected remote result paths (to download)
    depends_on: list[str] = []          # job_names this depends on (→ afterok DAG)
    resources: ResourceSpec = ResourceSpec()
    modules: list[str] = []
    conda_env: str | None = None

class SlurmJobStatus(BaseModel):
    job_name: str
    job_id: str | None = None
    state: str = "UNKNOWN"              # PENDING/RUNNING/COMPLETED/FAILED/TIMEOUT/CANCELLED
    exit_code: str | None = None
    submit_time: str | None = None
    end_time: str | None = None
    raw: str = ""
    @property
    def is_terminal(self) -> bool: ...
    @property
    def ok(self) -> bool:           # COMPLETED + exit 0
        ...

class RemoteExecutionResult(BaseModel):
    run_id: str
    remote_base: str
    jobs: list[SlurmJobStatus] = []
    all_ok: bool = False
    failed: list[str] = []             # job_names that did not succeed

class SyncedFile(BaseModel):
    remote_path: str
    local_path: str
    size: int = 0
    ok: bool = False                   # exists + size>0 (+ checksum if available)

class SyncedResultManifest(BaseModel):
    run_id: str
    downloaded: list[SyncedFile] = []
    missing: list[str] = []
    complete: bool = False

class ToolOutputParseResult(BaseModel):
    tool: str
    sample_id: str | None = None
    parsed_table_path: str | None = None
    n_records: int = 0
    ok: bool = True
    schema_version: str = "1"
    warnings: list[str] = []
```

These persist into the job ledger and into graph state (§ state additions).

---

## 7. Error handling (per failure mode)

Reuse Phase 2's **warn-and-continue + graceful-degradation** philosophy; classify
into the existing `errors`/`warnings` + `error_handler`.

| Failure | Detection | Recovery | Severity |
|---|---|---|---|
| SSH connect fails | non-zero ssh / timeout | retry w/ exponential backoff ×`hpc.retries`; reuse ControlMaster | critical if persists (can't run) |
| Upload fails | rsync exit ≠ 0 | rsync `--partial` resume + retry | critical if persists |
| `sbatch` fails | non-zero / no job id | parse stderr: malformed script → **critical** (needs fix); scheduler busy → retry | depends on cause |
| Job FAILED/TIMEOUT/OOM | `sacct` State/ExitCode | per-job **warn-and-continue**: mark outputs unavailable; downstream parser degrades that tool | non-critical (configurable) |
| Output files missing | `result_sync` expected vs found | record in `missing[]`; re-pull once; parser skips → `fell_back` | warn |
| Incomplete download | rsync checksum/size verify | re-download missing only; if still bad → mark unavailable | warn |
| Unexpected output format | parser try/except per file | catch → `ParseResult(ok=False)` + warning; never crash pipeline | warn |

**Cross-cutting:**
- **Idempotency/resume:** ledger prevents resubmission; controller restart
  re-attaches to RUNNING jobs.
- **Timeouts:** overall `hpc.max_wait` guards the monitor loop.
- **Atomic results:** only treat an output as "ready" if its job is `COMPLETED`
  (avoid downloading half-written files).

---

## 8. Local testing strategy (no HPC required)

**The `RemoteBackend` abstraction + fixture outputs = full local testability.**

- **`MockBackend`**: `upload`→copy into a temp "remote" dir; `submit`→place
  pre-canned fixture outputs in `results/`, return fake job id; `status`→scripted
  `PENDING→RUNNING→COMPLETED` (also a FAILED variant to test recovery);
  `download`→copy back. Selected via `hpc.backend: mock`.
- **Fixture fake tool outputs** under `tests/fixtures/`: real-format
  `*.kraken2.report`, Bracken `*.bracken`, `fastqc_data.txt`/summary,
  `*.diamond.tsv`, `samtools flagstat`, CheckV `quality_summary.tsv`. These drive
  the **parser tests** — the highest-value tests (parser correctness against real
  formats).
- **Test layers:**
  1. *unit* — each parser vs fixture → expected normalized table.
  2. *unit* — `SlurmJobStatus` parsing from sample `sacct`/`squeue` text.
  3. *unit* — `MockBackend` upload/submit/status/download.
  4. *unit* — SLURM script + dependency-DAG generation from `RemoteJobSpec`s.
  5. *integration* — full graph in `hpc` mode w/ `MockBackend` + fixtures →
     parsed tables → risk → report. **No real SSH/SLURM.**
- **Never auto-submit to real HPC in dev/CI:** backend defaults to `mock` in
  tests; `ssh` only when explicitly configured. A real-cluster smoke test is
  guarded behind an env var (e.g. `METAMAVS_HPC_SMOKE=1`) and skipped otherwise.

---

## 9. Implementation plan

**New modules**
```text
metamavs/remote/__init__.py
metamavs/remote/types.py          # the pydantic data structures (§6)
metamavs/remote/backends.py       # RemoteBackend ABC, SSHBackend, MockBackend
metamavs/remote/slurm.py          # script gen from RemoteJobSpec; sacct/squeue parse; DAG
metamavs/remote/job_ledger.py     # load/save jobs.json; resume logic
metamavs/parsers/__init__.py      # registry: tool -> parser
metamavs/parsers/base.py          # ParseResult helpers
metamavs/parsers/fastqc.py
metamavs/parsers/host_removal.py  # samtools flagstat
metamavs/parsers/kraken2.py
metamavs/parsers/bracken.py
metamavs/parsers/diamond.py
metamavs/parsers/checkv.py
metamavs/agents/remote_execution_agent.py
metamavs/agents/result_sync_agent.py
metamavs/agents/tool_output_parser_agent.py
```

**Edits to existing files**
- `config.py`: add `HPCConfig` (host, user, remote_base, backend=`ssh|mock`,
  default partition/time/mem, retries, poll_interval_s, max_wait_s, conda_env,
  modules); `ExecutionConfig.mode` gains `"hpc"`.
- `state.py`: add `remote_job_specs`, `remote_execution_result`,
  `synced_manifest`, `parse_results` (+ keep accumulators).
- `routing.py` + `graph.py`: register 3 nodes; add `mode_router` after the
  builder agents (hpc → remote_execution; else → taxonomy).
- 4 builder agents (`qc/host_removal/viral_detection/novel_virus`): in `hpc`
  mode append a `RemoteJobSpec` instead of executing (dry-run/local unchanged).
- `taxonomy_agent`/`abundance_agent`: read real parsed tables when present
  (already read CSVs by path — minimal change).
- `cli.py`: `--mode hpc`, `--remote-backend`, new `metamavs remote-status` cmd.

**New configs**
- `configs/example_hpc_config.yaml`

**New tests**
- `tests/fixtures/...` (fake outputs)
- `tests/test_parsers.py`, `tests/test_remote_backends.py`,
  `tests/test_slurm.py`, `tests/test_remote_graph.py`

**Development order (each step independently testable):**
1. `remote/types.py` + config + state additions.
2. `RemoteBackend` ABC + `MockBackend` (+ `SSHBackend`).
3. `remote/slurm.py` (script gen + status parsing) + `job_ledger.py`.
4. **Parsers + fixtures + parser tests** (pure local — biggest value first).
5. Three new agents.
6. `graph.py`/`routing.py` integration + `mode_router`.
7. Make 4 builder agents mode-aware.
8. Integration test (hpc mode + MockBackend + fixtures).
9. `example_hpc_config.yaml` + CLI + docs.
10. Optional guarded real-SSH smoke test.

---

## 10. Final recommended architecture & rationale

```text
┌────────────────────────── LOCAL (controller + brain) ──────────────────────────┐
│ LangGraph StateGraph                                                            │
│   input_manager → builders(emit RemoteJobSpec) → remote_execution →            │
│   result_sync → tool_output_parser → taxonomy → abundance → risk →             │
│   review? → report → final                                                     │
│ RemoteBackend (SSHBackend | MockBackend)   Job ledger (jobs.json)              │
└───────────────▲───────────────────────────────────────────────┬───────────────┘
        rsync up │ scripts + inputs                results (rsync) │ down
┌───────────────┴───────────────────────────────────────────────▼───────────────┐
│ HPC (executor only)   SLURM: sbatch DAG → FastQC/Kraken2/DIAMOND/VirSorter2…    │
│   $remote_base/metamavs/<run_id>/{inputs,scripts,work,results,logs}             │
│   tools via modules/conda · NO MetaMAVS Python here                            │
└─────────────────────────────────────────────────────────────────────────────────┘
```

**Why this beats "run everything on HPC":**
1. **Right tool for each job** — HPC does heavy compute; local does
   orchestration/parsing/reporting (which need no cluster).
2. **Dev velocity & testability** — 95% of work (graph, parsers, reports) is
   built/tested locally with `MockBackend`; no cluster needed; CI never touches HPC.
3. **Robustness** — login nodes kill long orchestrators and lack internet;
   a fragile Python+LangGraph env on HPC is avoided entirely.
4. **Minimal HPC footprint** — only self-contained bash + inputs cross over; no
   MetaMAVS install/version drift on the cluster.
5. **Portability** — swap clusters or go cloud by writing one new `RemoteBackend`;
   the graph and parsers are untouched.
6. **Resumability** — durable job ledger lets the controller restart and
   re-attach to multi-hour jobs.
7. **Consistency with Phases 1–2** — additive (a new mode + 3 nodes), dry-run
   preserved, graceful degradation, framework dependency still only in `graph.py`.

---

## 11. Key code skeletons

### 11.1 RemoteBackend abstraction (`metamavs/remote/backends.py`)
```python
from abc import ABC, abstractmethod

class RemoteBackend(ABC):
    @abstractmethod
    def run(self, command: str) -> tuple[int, str, str]: ...      # (rc, stdout, stderr)
    @abstractmethod
    def upload(self, local: str, remote: str) -> bool: ...        # rsync up
    @abstractmethod
    def download(self, remote: str, local: str) -> bool: ...      # rsync down
    @abstractmethod
    def exists(self, remote_path: str) -> bool: ...

class SSHBackend(RemoteBackend):
    def __init__(self, host, user=None, ssh_opts=None): ...
    def run(self, command):
        # subprocess: ssh <user@host> "<command>"
        ...
    def upload(self, local, remote):
        # subprocess: rsync -avz --partial --checksum <local> <user@host>:<remote>
        ...
    # download/exists similar

class MockBackend(RemoteBackend):
    """Fake HPC on the local FS for tests. `fixtures` maps remote result paths
    to local fixture files placed on 'submit'."""
    def __init__(self, root: Path, fixtures: dict[str, str] | None = None): ...
    def run(self, command):
        # interpret 'sbatch'→return fake parsable id; 'sacct'→scripted status
        ...
    def upload(self, local, remote): ...   # shutil.copy into root
    def download(self, remote, local): ...  # shutil.copy out of root
```

### 11.2 SLURM helpers (`metamavs/remote/slurm.py`)
```python
def render_job_script(spec: RemoteJobSpec, payload: list[str], remote_dir: str) -> str:
    """Render a self-contained #SBATCH bash script: headers + module/conda + cmds."""

def submit_dag(backend, specs: list[RemoteJobSpec], remote_dir) -> dict[str, str]:
    """sbatch --parsable each spec with --dependency=afterok:<dep ids>; return name→job_id."""

def parse_sacct(text: str) -> list[SlurmJobStatus]:
    """Parse `sacct --parsable2 --noheader --format=JobID,JobName,State,ExitCode`."""

def poll_until_terminal(backend, ledger, *, interval_s, max_wait_s) -> RemoteExecutionResult:
    """Loop sacct, update ledger each round, stop when all jobs terminal/timeout."""
```

### 11.3 Parser pattern (`metamavs/parsers/kraken2.py`)
```python
def parse_kraken2_report(path: str, sample_id: str) -> ToolOutputParseResult:
    """Parse a Kraken2 report into the normalized raw_viral_hits schema
    (sample_id, taxon_name, family, taxid, reads, ...). On malformed input
    return ToolOutputParseResult(ok=False, warnings=[...]) — never raise."""
```
Registry in `parsers/__init__.py`:
```python
PARSERS = {"kraken2": parse_kraken2_report, "bracken": parse_bracken, ...}
```

### 11.4 Agents (skeletons)
```python
# remote_execution_agent.py
def remote_execution_agent_node(state):
    specs = [RemoteJobSpec(**s) for s in state.get("remote_job_specs", [])]
    backend = make_backend(state)            # SSHBackend or MockBackend from config
    remote_dir = remote_run_dir(state)
    backend.run(f"mkdir -p {remote_dir}/...")
    for spec in specs:                        # upload inputs + scripts
        backend.upload(spec.script_local, spec.script_remote)
        for f in spec.input_files: backend.upload(f, ...)
    ledger = JobLedger(state["run_dir"])
    name2id = submit_dag(backend, specs, remote_dir); ledger.record(name2id)
    result = poll_until_terminal(backend, ledger, interval_s=..., max_wait_s=...)
    return {"remote_execution_result": result.model_dump(),
            "execution_reports": [...], "warnings": [...]}

# result_sync_agent.py
def result_sync_agent_node(state):
    backend = make_backend(state); manifest = SyncedResultManifest(run_id=...)
    for spec in specs_for(state):
        for out in spec.output_files:
            ok = backend.download(out, local_for(out))
            manifest.downloaded.append(SyncedFile(..., ok=ok))
            if not ok: manifest.missing.append(out)
    manifest.complete = not manifest.missing
    return {"synced_manifest": manifest.model_dump(), "warnings": [...]}

# tool_output_parser_agent.py
def tool_output_parser_agent_node(state):
    results = []
    for f in downloaded_files(state):
        parser = PARSERS.get(tool_of(f))
        results.append(parser(f, sample_of(f)) if parser else skip(f))
    # write normalized tables (raw_viral_hits.csv, qc_summary, ...) downstream agents read
    return {"parse_results": [r.model_dump() for r in results],
            "raw_viral_hits_path": ..., "qc_summary": ..., "warnings": [...]}
```

### 11.5 Mode routing (`routing.py`)
```python
def mode_router(state):
    if has_critical_error(state): return NODE_ERROR
    mode = state.get("config", {}).get("execution", {}).get("mode", "local")
    return NODE_REMOTE_EXEC if mode == "hpc" else NODE_TAXONOMY
```

### 11.6 Config additions (`config.py`)
```python
class HPCConfig(BaseModel):
    backend: Literal["ssh", "mock"] = "ssh"
    host: str | None = None
    user: str | None = None
    remote_base: str = "~/metamavs_runs"
    partition: str = "batch"
    conda_env: str | None = None
    modules: list[str] = []
    retries: int = 3
    poll_interval_s: int = 30
    max_wait_s: int = 86400
# ExecutionConfig.mode: Literal["local", "slurm", "hpc"]
# MetaMAVSConfig.hpc: HPCConfig = Field(default_factory=HPCConfig)
```

---

## 12. Open choices to confirm before implementation
1. **SSH transport:** subprocess `ssh`+`rsync` (recommended — uses your ssh
   config/keys) vs `paramiko` (pure-python dep, no rsync). Default: subprocess.
2. **Inputs already on HPC?** If FASTQ already live on cluster scratch, skip
   upload and reference paths in place (add `input.remote_data: true`).
3. **First parser set to implement:** suggest FastQC, samtools flagstat,
   Kraken2, Bracken, DIAMOND, CheckV (matches the example config tools).
4. **Durable checkpoint:** JSON ledger (Phase 3) now; `SqliteSaver` later if you
   want full LangGraph-level resume.
