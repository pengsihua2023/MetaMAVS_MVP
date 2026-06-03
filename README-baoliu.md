# MetaMAVS
MetaMAVS: A Metagenomic Multi-Agent Virus Surveillance System for Automated Viral Detection, Classification, and Epidemiological Risk Assessment
## 提示词
对，上面的提示词只说了“多智能体系统”，但**没有明确指定多智能体编程框架**。如果你希望采用 **LangGraph**，提示词应该直接写清楚：用 LangGraph 的 `StateGraph` 把每个 agent 设计成图节点，用 shared state 传递结果，用 conditional edges 控制流程，用 checkpoint 支持断点恢复和 human-in-the-loop 审核。LangGraph 官方也强调它适合构建持久化、可恢复、可人工干预的 agent 工作流。([LangChain 文档][1])

下面是修改后的 Claude Code 提示词，可以直接复制使用。

---

```text
You are an expert bioinformatics software architect, Python developer, LangGraph engineer, and AI multi-agent system designer.

I want to develop a research-grade software system named MetaMAVS.

Full name:
MetaMAVS: Metagenomic Multi-Agent Virus Surveillance System

Main technical framework:
Use LangGraph as the core multi-agent programming framework.

Important:
This project should NOT be only a collection of Python classes. It must use LangGraph to define a stateful multi-agent workflow.

The system should use:
- LangGraph StateGraph
- Shared graph state
- Agent nodes
- Conditional edges
- Checkpointing
- Human-in-the-loop review points
- Dry-run mode
- CLI execution
- Modular Python package structure

Goal:
Build a multi-agent system for virus surveillance based on wastewater or environmental metagenomic sequencing data. The system should process metagenomic data, detect known and potential viral signals, classify viruses taxonomically, summarize abundance trends, perform epidemiological risk assessment, and generate surveillance reports.

Project background:
I work on viral metagenomics, wastewater surveillance, and bioinformatics pipelines. I want MetaMAVS to combine traditional metagenomic analysis pipelines with AI multi-agent coordination. The system should eventually support virus detection, taxonomic classification, quality control, abundance analysis, trend monitoring, risk assessment, and automated report generation.

Core LangGraph design:
Implement the workflow as a LangGraph state machine.

Each major analysis step should be a LangGraph node.

The graph state should store:
- config
- sample manifest
- sample metadata
- file paths
- QC results
- host removal results
- viral detection results
- taxonomy classification results
- abundance results
- novel virus candidate results
- risk assessment results
- report paths
- errors
- warnings
- execution log
- current workflow status

Expected LangGraph nodes / agents:

1. input_manager_node
Role:
- Accept FASTQ files, metadata files, and configuration files.
- Validate sample names, file paths, sequencing type, and metadata consistency.
- Produce a clean sample manifest.
Output:
- validated_manifest
- input_summary
- warnings

2. qc_agent_node
Role:
- Generate or run commands for FastQC, fastp, and MultiQC.
- Summarize read quality, adapter contamination, read length, sequencing depth.
- Decide whether samples pass QC thresholds.
Output:
- qc_commands
- qc_summary
- qc_pass_fail

3. host_removal_agent_node
Role:
- Generate or run host-removal commands using Bowtie2, BWA, or minimap2.
- Support human, animal, or custom host references.
- Report host-read percentage and non-host read counts.
Output:
- host_removal_commands
- host_removal_summary
- non_host_fastq_paths

4. viral_detection_agent_node
Role:
- Generate or run viral detection commands using Kraken2, KrakenUniq, Centrifuge, DIAMOND, BLAST, or RVDB-based search.
- Support nucleotide-level and protein-level viral detection.
- Output candidate viral taxa with read counts and confidence scores.
Output:
- viral_detection_commands
- raw_viral_hits
- candidate_viral_taxa

5. taxonomy_classification_agent_node
Role:
- Normalize and clean taxonomy results.
- Map detected taxa to family, genus, species, accession, and taxid information.
- Identify likely false positives, environmental phages, low-complexity hits, and possible contamination.
Output:
- cleaned_taxonomy_table
- false_positive_flags
- taxonomy_summary

6. abundance_analysis_agent_node
Role:
- Normalize viral abundance using reads per million, genome length correction, or PMMoV normalization if metadata are available.
- Compare abundance across samples, locations, and time points.
- Generate trend tables.
Output:
- abundance_table
- trend_summary
- abundance_plots_or_plot_specs

7. novel_virus_screening_agent_node
Role:
- Identify suspicious unclassified viral contigs or divergent viral signals.
- Support assembly-based analysis using MEGAHIT or metaSPAdes.
- Prepare commands for VirSorter2, VIBRANT, geNomad, CheckV, or DeepVirFinder.
- Summarize possible novel viral candidates.
Output:
- assembly_commands
- novel_virus_commands
- novel_candidate_table
- novel_candidate_summary

8. risk_assessment_agent_node
Role:
- Combine abundance, trend, taxonomy, host range, known pathogen status, and novelty.
- Assign simple risk levels:
  Low, Medium, High, Critical.
- Explain why each virus receives its risk level.
Output:
- risk_table
- risk_summary
- recommended_followup_actions

9. human_review_node
Role:
- Implement a human-in-the-loop checkpoint.
- Pause or mark results for review when:
  - a high-risk pathogen is detected
  - a novel virus candidate is detected
  - QC failure occurs
  - abundance sharply increases
  - taxonomy confidence is low
- In the first prototype, this can be implemented as a simple CLI review step or a simulated approval mechanism.
Output:
- review_decision
- reviewer_notes
- approved_for_report

10. report_writer_agent_node
Role:
- Generate Markdown and HTML reports.
- Include:
  - project summary
  - sample summary
  - QC summary
  - host removal summary
  - detected viruses
  - taxonomy summary
  - abundance trends
  - novel virus candidates
  - epidemiological risk assessment
  - human review notes
  - recommended follow-up actions
Output:
- markdown_report_path
- html_report_path

11. error_handler_node
Role:
- Handle failed steps gracefully.
- Save error messages.
- Decide whether the workflow can continue or should stop.
Output:
- updated errors
- workflow status

12. final_summary_node
Role:
- Summarize the full run.
- Print final paths and key results.
Output:
- final_summary

LangGraph routing requirements:
Create a graph with the following basic flow:

START
→ input_manager_node
→ qc_agent_node
→ host_removal_agent_node
→ viral_detection_agent_node
→ taxonomy_classification_agent_node
→ abundance_analysis_agent_node
→ novel_virus_screening_agent_node
→ risk_assessment_agent_node
→ conditional_review_router

The conditional_review_router should route to:
- human_review_node if risk is High/Critical, if novel candidates exist, or if QC failed
- report_writer_agent_node directly if no review is needed

Then:
human_review_node → report_writer_agent_node
report_writer_agent_node → final_summary_node
final_summary_node → END

Also include an error route:
Any node may add errors to the state.
If a critical error occurs, route to error_handler_node.
error_handler_node may either stop the workflow or continue depending on the error severity.

Technical requirements:
- Python 3.11 or newer
- LangGraph
- LangChain Core only if needed
- pydantic for schemas and config validation
- pandas for table processing
- PyYAML or ruamel.yaml for YAML config
- pathlib for file paths
- logging instead of print statements
- typer or argparse for CLI
- rich optional for better terminal output
- pytest for unit tests

External bioinformatics tools:
The first version should not require actual installation of all tools.
Implement dry-run mode first.
In dry-run mode, the system should generate commands but not execute them.

Supported tools to generate commands for:
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

Project structure:

MetaMAVS/
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
    graph.py
    state.py
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
      final_summary.py
      error_handler.py
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

Implementation requirements for the first working version:
1. Create the full project skeleton.
2. Implement configuration loading from YAML.
3. Implement sample manifest validation.
4. Implement MetaMAVSState as a TypedDict or pydantic-compatible state object suitable for LangGraph.
5. Implement each agent as a LangGraph node function.
6. Implement graph.py to build and compile the LangGraph StateGraph.
7. Implement routing.py for conditional routing.
8. Implement dry-run command generation for each bioinformatics step.
9. Implement checkpointing using LangGraph MemorySaver for the first prototype.
10. Implement a human review node as a simple CLI-based or simulated review step.
11. Save intermediate outputs as CSV and JSON files.
12. Generate a final Markdown report.
13. Provide a CLI command:

   metamavs run --config configs/example_config.yaml --dry-run

14. Provide another command to visualize or describe the graph:

   metamavs graph --config configs/example_config.yaml

15. Provide example input files and example output report.
16. Include clear instructions in README.md.
17. Include unit tests for config loading, state updates, routing logic, and graph compilation.

Coding style:
- Keep the first version simple and runnable.
- Do not over-engineer the first prototype.
- Avoid unnecessary cloud dependencies.
- Do not require OpenAI, Anthropic, or other LLM API keys in the first version.
- Design the code so that LLM-based reasoning agents can be added later.
- Every node should receive the current graph state and return a partial state update.
- Every node should write clear logs.
- Every node should be testable independently.

Important design principle:
The first version of MetaMAVS should be a deterministic LangGraph-based bioinformatics workflow. Later versions can add LLM reasoning inside selected nodes, such as taxonomy interpretation, false-positive review, risk explanation, and report writing.

Please begin by:
1. Explaining the proposed LangGraph-based architecture.
2. Creating the full project skeleton.
3. Writing the core state.py, config.py, schemas.py, routing.py, and graph.py files.
4. Implementing all node functions.
5. Implementing the CLI.
6. Creating example config and manifest files.
7. Creating tests.
8. Explaining how to run the first prototype.
```

---

我建议你在 Claude Code 里**先不要一次性要求它完成所有 bioinformatics 工具的真实运行**。第一版最好是：

**LangGraph + dry-run command generator + report generator**

也就是先让系统跑通：

```bash
metamavs run --config configs/example_config.yaml --dry-run
```

然后第二阶段再让 Claude Code 增加真实执行：

```text
Now extend MetaMAVS from dry-run mode to real execution mode.
Implement command execution with subprocess, tool availability checking, output validation, and SLURM job script generation.
```

如果你的目标是将来写论文，项目介绍可以改成：

**MetaMAVS is implemented as a LangGraph-based multi-agent workflow for metagenomic virus surveillance, integrating quality control, host depletion, viral detection, taxonomic interpretation, abundance analysis, novel-virus screening, risk assessment, and automated reporting.**

[1]: https://docs.langchain.com/oss/python/langgraph/persistence?utm_source=chatgpt.com "Persistence - Docs by LangChain"
