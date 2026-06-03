# CLAUDE.md

## Project Name

MetaMAVS: Metagenomic Multi-Agent Virus Surveillance System

## Project Purpose

MetaMAVS is a research-grade, LangGraph-based multi-agent workflow system for viral surveillance using wastewater, environmental, or clinical metagenomic sequencing data.

The system is designed to support:

- metagenomic sample input validation
- sequencing quality control
- host-read removal
- viral read detection
- viral taxonomic classification
- false-positive filtering
- viral abundance normalization
- temporal trend analysis
- novel virus / variant candidate screening
- epidemiological risk assessment
- automated Markdown / HTML report generation
- future integration with LLM-based reasoning agents

The first version should be a deterministic, local, dry-run-capable prototype. It should not require cloud services, paid APIs, or root privileges.

---

## Primary Development Framework

Use **LangGraph** as the core multi-agent workflow framework.

This project must not be implemented as only independent Python classes. The core workflow should be represented as a LangGraph `StateGraph`.

Each major analysis step should be a LangGraph node.

Required LangGraph concepts:

- `StateGraph`
- shared graph state
- node functions
- conditional routing
- checkpointing
- error routing
- human-in-the-loop review node
- dry-run execution mode

The first version should use deterministic node logic. LLM-based interpretation can be added later.

---

## High-Level Workflow

The basic workflow should be:

```text
START
  -> input_manager_node
  -> qc_agent_node
  -> host_removal_agent_node
  -> viral_detection_agent_node
  -> taxonomy_classification_agent_node
  -> abundance_analysis_agent_node
  -> novel_virus_screening_agent_node
  -> risk_assessment_agent_node
  -> conditional_review_router
      -> human_review_node, if needed
      -> report_writer_agent_node, if review not needed
  -> report_writer_agent_node
  -> final_summary_node
  -> END
```

Critical errors should route to:

```text
error_handler_node
```

The error handler may stop the workflow or allow continuation depending on error severity.

---

## Core Agents / Nodes

### 1. input_manager_node

Responsibilities:

- Load and validate input manifest.
- Validate sample IDs.
- Validate FASTQ file paths.
- Validate paired-end or single-end consistency.
- Validate metadata columns.
- Produce a clean sample manifest.

Outputs added to state:

- `validated_manifest_path`
- `sample_summary`
- `warnings`
- `errors`

---

### 2. qc_agent_node

Responsibilities:

- Generate dry-run commands for FastQC, fastp, and MultiQC.
- Later support real command execution.
- Summarize expected QC outputs.
- Mark samples as pass/fail using simple thresholds when real results exist.

Outputs added to state:

- `qc_commands`
- `qc_summary_path`
- `qc_pass_fail`
- `warnings`
- `errors`

---

### 3. host_removal_agent_node

Responsibilities:

- Generate dry-run commands for Bowtie2, BWA, or minimap2.
- Support human, animal, or custom host references.
- Track expected non-host FASTQ outputs.
- Later support real execution and log parsing.

Outputs added to state:

- `host_removal_commands`
- `host_removal_summary_path`
- `non_host_fastq_paths`
- `warnings`
- `errors`

---

### 4. viral_detection_agent_node

Responsibilities:

- Generate dry-run commands for viral detection tools.
- Supported tools may include Kraken2, KrakenUniq, Centrifuge, DIAMOND, BLAST, and RVDB-based searches.
- Produce placeholder or parsed viral hit tables depending on mode.

Outputs added to state:

- `viral_detection_commands`
- `raw_viral_hits_path`
- `candidate_viral_taxa_path`
- `warnings`
- `errors`

---

### 5. taxonomy_classification_agent_node

Responsibilities:

- Normalize taxonomic results.
- Map detected taxa to taxonomic ranks.
- Identify possible false positives.
- Flag likely environmental phages, low-complexity hits, and contaminants.
- Avoid overclaiming pathogen detection from weak evidence.

Outputs added to state:

- `cleaned_taxonomy_table_path`
- `false_positive_flags_path`
- `taxonomy_summary`
- `warnings`
- `errors`

---

### 6. abundance_analysis_agent_node

Responsibilities:

- Normalize viral abundance.
- Support reads per million.
- Later support genome-length correction and PMMoV normalization.
- Compare samples across time points and locations.
- Generate trend-ready tables.

Outputs added to state:

- `abundance_table_path`
- `trend_summary_path`
- `plot_specs_path`
- `warnings`
- `errors`

---

### 7. novel_virus_screening_agent_node

Responsibilities:

- Generate dry-run assembly and viral contig screening commands.
- Supported tools may include MEGAHIT, metaSPAdes, VirSorter2, VIBRANT, geNomad, CheckV, and DeepVirFinder.
- Identify suspicious unclassified viral signals.
- Prepare candidate tables.

Outputs added to state:

- `assembly_commands`
- `novel_virus_commands`
- `novel_candidate_table_path`
- `novel_candidate_summary`
- `warnings`
- `errors`

---

### 8. risk_assessment_agent_node

Responsibilities:

- Combine taxonomy, abundance, trend, novelty, pathogen status, and confidence.
- Assign risk levels:

```text
Low
Medium
High
Critical
```

- Provide transparent explanations.
- Do not exaggerate weak metagenomic signals.

Outputs added to state:

- `risk_table_path`
- `risk_summary`
- `recommended_followup_actions`
- `warnings`
- `errors`

---

### 9. human_review_node

Responsibilities:

- Act as a human-in-the-loop checkpoint.
- Trigger review when:

```text
risk level is High or Critical
novel virus candidates are detected
QC failure occurs
taxonomy confidence is low
abundance sharply increases
critical warnings exist
```

- First prototype may simulate approval in dry-run mode.
- Later versions may ask the user interactively in CLI.

Outputs added to state:

- `review_required`
- `review_decision`
- `reviewer_notes`
- `approved_for_report`

---

### 10. report_writer_agent_node

Responsibilities:

Generate final reports in:

- Markdown
- HTML

Reports should include:

- project summary
- sample summary
- QC summary
- host removal summary
- viral detection summary
- taxonomy summary
- abundance trends
- novel virus candidates
- risk assessment
- human review notes
- recommended follow-up actions
- reproducibility information
- software version
- config path
- run timestamp

Outputs added to state:

- `markdown_report_path`
- `html_report_path`

---

### 11. error_handler_node

Responsibilities:

- Collect and classify errors.
- Decide whether the workflow can continue.
- Save error logs.
- Prevent silent failures.

Outputs added to state:

- `workflow_status`
- `error_summary`
- `can_continue`

---

### 12. final_summary_node

Responsibilities:

- Print or return a concise final run summary.
- Show report paths.
- Show key warnings.
- Show high-risk detections if any.

Outputs added to state:

- `final_summary`

---

## Expected Project Structure

Use this structure unless there is a strong reason to change it:

```text
MetaMAVS/
  CLAUDE.md
  AGENTS.md
  README.md
  pyproject.toml
  configs/
    example_config.yaml
  data/
    example_manifest.csv
  metamavs/
    __init__.py
    cli.py
    config.py
    schemas.py
    state.py
    graph.py
    routing.py
    agents/
      __init__.py
      input_manager.py
      qc_agent.py
      host_removal_agent.py
      viral_detection_agent.py
      taxonomy_agent.py
      abundance_agent.py
      novel_virus_agent.py
      risk_assessment_agent.py
      human_review.py
      report_writer_agent.py
      error_handler.py
      final_summary.py
    utils/
      __init__.py
      command_runner.py
      logging_utils.py
      file_utils.py
      taxonomy_utils.py
      report_utils.py
    workflows/
      __init__.py
      local_workflow.py
      slurm_workflow.py
  reports/
  tests/
    test_config.py
    test_state.py
    test_graph.py
    test_routing.py
    test_manifest_validation.py
```

---

## Development Priorities

### Phase 1: Minimal Runnable Prototype

Implement first:

- project skeleton
- YAML config loading
- manifest validation
- LangGraph state definition
- LangGraph graph construction
- all node functions with dry-run behavior
- command generation
- intermediate CSV / JSON outputs
- Markdown report generation
- CLI command:

```bash
metamavs run --config configs/example_config.yaml --dry-run
```

Also implement:

```bash
metamavs graph --config configs/example_config.yaml
```

The graph command should describe the workflow structure.

---

### Phase 2: Real Command Execution

After dry-run mode works, add:

- subprocess-based command execution
- command logging
- tool availability checking
- exit-code validation
- output file validation
- failed-command recovery
- SLURM script generation

---

### Phase 3: Bioinformatics Expansion

Add support for:

- FastQC
- fastp
- MultiQC
- Bowtie2
- BWA
- minimap2
- Kraken2
- KrakenUniq
- Centrifuge
- DIAMOND
- BLAST
- MEGAHIT
- metaSPAdes
- VirSorter2
- VIBRANT
- geNomad
- CheckV
- DeepVirFinder

---

### Phase 4: Intelligent Interpretation

Later versions may add LLM-assisted reasoning for:

- taxonomy interpretation
- false-positive explanation
- risk explanation
- surveillance narrative writing
- literature-aware pathogen interpretation
- public-health alert summarization

Do not require LLM API keys in Phase 1.

---

## Coding Standards

Use:

- Python 3.11+
- LangGraph
- pydantic
- pandas
- PyYAML or ruamel.yaml
- pathlib
- logging
- typer or argparse
- pytest

General rules:

- Use `pathlib.Path`, not string path concatenation.
- Use `logging`, not `print`, except CLI final output.
- Use pydantic models for config validation.
- Keep functions small and testable.
- Every LangGraph node should accept the current state and return a partial state update.
- Every node should be independently testable.
- Do not hard-code absolute paths.
- Do not assume sudo/root access.
- Do not require external bioinformatics tools in dry-run mode.
- Avoid unnecessary cloud dependencies.
- Avoid hidden global state.
- Avoid writing large monolithic files.
- Prefer explicit schemas over loosely structured dictionaries.

---

## State Design Guidelines

Define `MetaMAVSState` in `metamavs/state.py`.

The state may be a `TypedDict` or pydantic-compatible structure.

It should include fields similar to:

```python
config: dict
run_id: str
run_dir: str
manifest_path: str
validated_manifest_path: str | None
sample_summary: dict
qc_commands: list[str]
qc_summary_path: str | None
qc_pass_fail: dict
host_removal_commands: list[str]
host_removal_summary_path: str | None
non_host_fastq_paths: dict
viral_detection_commands: list[str]
raw_viral_hits_path: str | None
candidate_viral_taxa_path: str | None
cleaned_taxonomy_table_path: str | None
false_positive_flags_path: str | None
taxonomy_summary: dict
abundance_table_path: str | None
trend_summary_path: str | None
assembly_commands: list[str]
novel_virus_commands: list[str]
novel_candidate_table_path: str | None
novel_candidate_summary: dict
risk_table_path: str | None
risk_summary: dict
recommended_followup_actions: list[str]
review_required: bool
review_decision: str | None
reviewer_notes: str | None
approved_for_report: bool
markdown_report_path: str | None
html_report_path: str | None
warnings: list[str]
errors: list[dict]
workflow_status: str
final_summary: dict
```

Keep this state explicit and well documented.

---

## Config Design Guidelines

The YAML config should include:

```yaml
project:
  name: MetaMAVS
  run_name: example_run
  output_dir: reports/example_run

input:
  manifest: data/example_manifest.csv
  sequencing_type: paired_end

execution:
  dry_run: true
  mode: local
  threads: 8

tools:
  qc:
    fastqc: true
    fastp: true
    multiqc: true
  host_removal:
    tool: bowtie2
    host_reference: /path/to/host/reference
  viral_detection:
    tools:
      - kraken2
      - diamond
    kraken2_db: /path/to/kraken2/viral_db
    diamond_db: /path/to/rvdb.dmnd
  assembly:
    enabled: true
    assembler: megahit
  novel_virus_screening:
    enabled: true
    tools:
      - virsorter2
      - checkv

risk:
  high_risk_pathogens:
    - SARS-CoV-2
    - Influenza A virus
    - Influenza B virus
    - Norovirus
    - Enterovirus
  review_on_high_risk: true
  review_on_novel_candidates: true

report:
  formats:
    - markdown
    - html
```

---

## Manifest Design Guidelines

The example manifest should include columns such as:

```csv
sample_id,read1,read2,collection_date,location,sample_type
sample_001,data/sample_001_R1.fastq.gz,data/sample_001_R2.fastq.gz,2026-01-01,site_A,wastewater
sample_002,data/sample_002_R1.fastq.gz,data/sample_002_R2.fastq.gz,2026-01-08,site_A,wastewater
```

Validation rules:

- `sample_id` must be unique.
- `read1` is required.
- `read2` is required for paired-end mode.
- `collection_date` should be parseable as a date if present.
- Paths may be allowed to not exist only in dry-run mode.
- In real execution mode, input files must exist.

---

## CLI Requirements

Use Typer or argparse.

Required commands:

```bash
metamavs run --config configs/example_config.yaml --dry-run
```

```bash
metamavs graph --config configs/example_config.yaml
```

Optional future commands:

```bash
metamavs validate --config configs/example_config.yaml
metamavs init
metamavs report --run-dir reports/example_run
```

---

## Testing Requirements

Use pytest.

Minimum tests:

- config loading works
- invalid config fails clearly
- manifest validation works
- duplicate sample IDs are rejected
- paired-end manifest requires read2
- LangGraph compiles successfully
- conditional routing sends high-risk cases to human review
- conditional routing skips human review for low-risk clean runs
- dry-run command generation produces expected commands
- report writer creates Markdown report

Run tests with:

```bash
pytest
```

---

## Bioinformatics Safety and Scientific Caution

This project is for research and surveillance support.

The system must not overstate results.

When writing reports:

- Use "detected signal" instead of "confirmed infection" unless confirmatory evidence exists.
- Use "candidate viral taxon" when classification confidence is limited.
- Flag low-read-count results.
- Flag likely contamination.
- Flag environmental phages separately from human pathogens.
- Recommend confirmatory testing for high-risk detections.
- Do not make clinical diagnoses.
- Do not claim outbreak confirmation from metagenomic reads alone.

Risk assessment should be transparent and explainable.

---

## HPC / SLURM Compatibility

The project should be compatible with HPC environments.

Do not assume:

- sudo access
- Docker access
- internet access on compute nodes
- root privileges

Prefer:

- local paths
- conda/mamba environments
- Apptainer/Singularity compatibility
- SLURM job script generation
- dry-run command generation

Future SLURM support should include:

```bash
metamavs slurm --config configs/example_config.yaml
```

---

## Logging and Outputs

Each run should create a run directory:

```text
reports/<run_name>/
  logs/
  intermediate/
  commands/
  tables/
  report.md
  report.html
  state.json
```

Write:

- command logs
- node-level logs
- final state JSON
- summary tables
- final reports

---

## Development Behavior for Claude Code

When working on this project:

1. First inspect the repository structure.
2. Read this `CLAUDE.md`.
3. Do not rewrite the entire project unless asked.
4. Prefer small, incremental changes.
5. Keep the code runnable after each major change.
6. After modifying code, run relevant tests if possible.
7. If tests cannot be run, explain why.
8. Do not invent external files that are not created.
9. Do not require unavailable databases in the first prototype.
10. Preserve dry-run mode.
11. Preserve LangGraph as the central workflow framework.
12. Do not replace LangGraph with a simple sequential script.
13. Keep public-health language cautious and scientifically accurate.

---

## Definition of Done for Phase 1

Phase 1 is complete when:

- `metamavs run --config configs/example_config.yaml --dry-run` runs successfully.
- The LangGraph workflow compiles.
- All node functions execute in order.
- Conditional review routing works.
- Intermediate output files are created.
- A final Markdown report is created.
- Tests for config, state, graph, routing, and manifest validation pass.
- README explains installation and usage.
