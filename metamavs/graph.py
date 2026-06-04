"""Construct and compile the MetaMAVS LangGraph ``StateGraph``.

The graph is the heart of MetaMAVS: a stateful multi-agent workflow rather than
a plain sequential script. Each agent is a node; the linear backbone is guarded
by conditional error edges; after the command-builder agents a **mode router**
either runs the Phase 3 remote (HPC) stage or proceeds locally; risk assessment
branches to human review when needed; and the error handler can either resume to
a best-effort report or jump straight to the final summary.
"""

from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from .agents import (
    abundance_agent_node,
    error_handler_node,
    final_summary_node,
    host_removal_agent_node,
    human_review_node,
    input_manager_node,
    novel_virus_screening_agent_node,
    qc_agent_node,
    remote_execution_agent_node,
    report_writer_agent_node,
    result_sync_agent_node,
    risk_assessment_agent_node,
    taxonomy_classification_agent_node,
    tool_output_parser_agent_node,
    viral_detection_agent_node,
)
from .routing import (
    NODE_ABUNDANCE,
    NODE_ERROR,
    NODE_FINAL,
    NODE_HOST,
    NODE_INPUT,
    NODE_NOVEL,
    NODE_PARSER,
    NODE_QC,
    NODE_REMOTE_EXEC,
    NODE_REPORT,
    NODE_RESULT_SYNC,
    NODE_REVIEW,
    NODE_RISK,
    NODE_TAXONOMY,
    NODE_VIRAL,
    error_handler_router,
    make_step_router,
    mode_router,
    review_router,
)
from .state import MetaMAVSState

# Pre-mode backbone: command-builder agents (input → qc → host → viral).
_PRE = [
    (NODE_INPUT, input_manager_node, NODE_QC),
    (NODE_QC, qc_agent_node, NODE_HOST),
    (NODE_HOST, host_removal_agent_node, NODE_VIRAL),
]
# Post-mode analysis backbone (taxonomy → abundance → novel → risk).
_POST = [
    (NODE_TAXONOMY, taxonomy_classification_agent_node, NODE_ABUNDANCE),
    (NODE_ABUNDANCE, abundance_agent_node, NODE_NOVEL),
    (NODE_NOVEL, novel_virus_screening_agent_node, NODE_RISK),
]
# Phase 3 remote chain (only traversed in hpc mode).
_REMOTE = [
    (NODE_REMOTE_EXEC, remote_execution_agent_node, NODE_RESULT_SYNC),
    (NODE_RESULT_SYNC, result_sync_agent_node, NODE_PARSER),
    (NODE_PARSER, tool_output_parser_agent_node, NODE_TAXONOMY),
]


def build_graph() -> StateGraph:
    """Build (but do not compile) the MetaMAVS ``StateGraph``."""

    graph = StateGraph(MetaMAVSState)

    # Register nodes.
    for name, fn, _ in _PRE + _POST + _REMOTE:
        graph.add_node(name, fn)
    graph.add_node(NODE_VIRAL, viral_detection_agent_node)
    graph.add_node(NODE_RISK, risk_assessment_agent_node)
    graph.add_node(NODE_REVIEW, human_review_node)
    graph.add_node(NODE_REPORT, report_writer_agent_node)
    graph.add_node(NODE_ERROR, error_handler_node)
    graph.add_node(NODE_FINAL, final_summary_node)

    graph.add_edge(START, NODE_INPUT)

    # Pre-mode builders with error diversion.
    for name, _, nxt in _PRE:
        graph.add_conditional_edges(name, make_step_router(nxt), {nxt: nxt, NODE_ERROR: NODE_ERROR})

    # After viral_detection: route on execution.mode (hpc → remote stage; else → taxonomy).
    graph.add_conditional_edges(
        NODE_VIRAL,
        mode_router,
        {NODE_REMOTE_EXEC: NODE_REMOTE_EXEC, NODE_TAXONOMY: NODE_TAXONOMY, NODE_ERROR: NODE_ERROR},
    )

    # Remote chain (hpc mode) → taxonomy, each guarded.
    for name, _, nxt in _REMOTE:
        graph.add_conditional_edges(name, make_step_router(nxt), {nxt: nxt, NODE_ERROR: NODE_ERROR})

    # Analysis backbone with error diversion.
    for name, _, nxt in _POST:
        graph.add_conditional_edges(name, make_step_router(nxt), {nxt: nxt, NODE_ERROR: NODE_ERROR})

    # Risk → conditional review router.
    graph.add_conditional_edges(
        NODE_RISK,
        review_router,
        {NODE_REVIEW: NODE_REVIEW, NODE_REPORT: NODE_REPORT, NODE_ERROR: NODE_ERROR},
    )
    graph.add_edge(NODE_REVIEW, NODE_REPORT)

    # Error handler → best-effort report or finalize.
    graph.add_conditional_edges(
        NODE_ERROR,
        error_handler_router,
        {NODE_REPORT: NODE_REPORT, NODE_FINAL: NODE_FINAL},
    )

    graph.add_edge(NODE_REPORT, NODE_FINAL)
    graph.add_edge(NODE_FINAL, END)

    return graph


def compile_graph(checkpointer: MemorySaver | None = None):
    """Compile the graph with an in-memory checkpointer (Phase 1 default)."""

    if checkpointer is None:
        checkpointer = MemorySaver()
    return build_graph().compile(checkpointer=checkpointer)


def describe_graph() -> str:
    """Return a human-readable description of the workflow structure."""

    lines = ["MetaMAVS LangGraph workflow", "=" * 32, "", "Nodes (in execution order):"]
    order = [NODE_INPUT, NODE_QC, NODE_HOST, NODE_VIRAL,
             NODE_REMOTE_EXEC, NODE_RESULT_SYNC, NODE_PARSER,
             NODE_TAXONOMY, NODE_ABUNDANCE, NODE_NOVEL, NODE_RISK,
             NODE_REVIEW, NODE_REPORT, NODE_FINAL, NODE_ERROR]
    for i, n in enumerate(order, 1):
        lines.append(f"  {i:2d}. {n}")
    lines += [
        "",
        "Edges:",
        "  START -> input_manager",
        "  input_manager -> qc_agent -> host_removal_agent -> viral_detection_agent",
        "  viral_detection_agent -> [mode_router]",
        "      hpc:   -> remote_execution_agent -> result_sync_agent -> tool_output_parser_agent -> taxonomy_agent",
        "      local: -> taxonomy_agent",
        "  taxonomy_agent -> abundance_agent -> novel_virus_agent -> risk_assessment_agent",
        "  risk_assessment_agent -> human_review        [if review required]",
        "  risk_assessment_agent -> report_writer_agent [if no review needed]",
        "  human_review -> report_writer_agent -> final_summary -> END",
        "  <any node> -> error_handler on critical error",
        "  error_handler -> report_writer_agent [can continue] | final_summary [stop]",
    ]
    return "\n".join(lines)
