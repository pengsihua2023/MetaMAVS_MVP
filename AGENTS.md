# AGENTS.md

## Project

MetaMAVS: Metagenomic Multi-Agent Virus Surveillance System

This is a Python, LangGraph-based multi-agent workflow for viral surveillance using metagenomic sequencing data.

## Setup Commands

Install in editable mode:

```bash
pip install -e ".[dev]"
```

Run tests:

```bash
pytest
```

Run dry-run workflow:

```bash
metamavs run --config configs/example_config.yaml --dry-run
```

Describe graph:

```bash
metamavs graph --config configs/example_config.yaml
```

## Core Requirements

- Use Python 3.11+.
- Use LangGraph as the central workflow framework.
- Keep dry-run mode functional.
- Do not require external bioinformatics tools for the first prototype.
- Do not require cloud APIs or LLM API keys for the first prototype.
- Use pydantic for config/schema validation.
- Use pandas for table processing.
- Use pathlib for paths.
- Use logging instead of print statements except for CLI output.
- Use pytest for tests.

## Architecture

The workflow should be implemented as a LangGraph `StateGraph`.

Main nodes:

- input_manager_node
- qc_agent_node
- host_removal_agent_node
- viral_detection_agent_node
- taxonomy_classification_agent_node
- abundance_analysis_agent_node
- novel_virus_screening_agent_node
- risk_assessment_agent_node
- human_review_node
- report_writer_agent_node
- error_handler_node
- final_summary_node

## Development Rules

- Make small, incremental changes.
- Do not replace LangGraph with a plain sequential script.
- Preserve existing CLI behavior.
- Preserve tests or update them when behavior changes.
- Avoid hard-coded absolute paths.
- Do not assume sudo/root access.
- Keep reports scientifically cautious.
- Do not claim confirmed infection or outbreak from metagenomic reads alone.

## Scientific Language

Prefer cautious wording:

- "viral signal detected"
- "candidate viral taxon"
- "putative novel viral contig"
- "requires confirmatory testing"

Avoid overclaiming:

- "confirmed outbreak"
- "confirmed infection"
- "clinical diagnosis"
