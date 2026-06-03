"""Construct and compile the MetaMAVS LangGraph ``StateGraph``.

The graph is the heart of MetaMAVS: a stateful multi-agent workflow rather than
a plain sequential script. Each agent is a node; the linear backbone is guarded
by conditional error edges; risk assessment branches to human review when
needed; and the error handler can either resume to a best-effort report or jump
straight to the final summary.
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
    report_writer_agent_node,
    risk_assessment_agent_node,
    taxonomy_classification_agent_node,
    viral_detection_agent_node,
)
from .routing import (
    NODE_ABUNDANCE,
    NODE_ERROR,
    NODE_FINAL,
    NODE_HOST,
    NODE_INPUT,
    NODE_NOVEL,
    NODE_QC,
    NODE_REPORT,
    NODE_REVIEW,
    NODE_RISK,
    NODE_TAXONOMY,
    NODE_VIRAL,
    error_handler_router,
    make_step_router,
    review_router,
)
from .state import MetaMAVSState

# Linear backbone: (node_name, node_fn, next_node_in_chain).
_BACKBONE = [
    (NODE_INPUT, input_manager_node, NODE_QC),
    (NODE_QC, qc_agent_node, NODE_HOST),
    (NODE_HOST, host_removal_agent_node, NODE_VIRAL),
    (NODE_VIRAL, viral_detection_agent_node, NODE_TAXONOMY),
    (NODE_TAXONOMY, taxonomy_classification_agent_node, NODE_ABUNDANCE),
    (NODE_ABUNDANCE, abundance_agent_node, NODE_NOVEL),
    (NODE_NOVEL, novel_virus_screening_agent_node, NODE_RISK),
]


def build_graph() -> StateGraph:
    """Build (but do not compile) the MetaMAVS ``StateGraph``."""

    graph = StateGraph(MetaMAVSState)

    # Register all nodes.
    for name, fn, _ in _BACKBONE:
        graph.add_node(name, fn)
    graph.add_node(NODE_RISK, risk_assessment_agent_node)
    graph.add_node(NODE_REVIEW, human_review_node)
    graph.add_node(NODE_REPORT, report_writer_agent_node)
    graph.add_node(NODE_ERROR, error_handler_node)
    graph.add_node(NODE_FINAL, final_summary_node)

    # Entry point.
    graph.add_edge(START, NODE_INPUT)

    # Linear backbone with per-node error diversion.
    for name, _, nxt in _BACKBONE:
        graph.add_conditional_edges(
            name,
            make_step_router(nxt),
            {nxt: nxt, NODE_ERROR: NODE_ERROR},
        )

    # Risk assessment -> conditional review router.
    graph.add_conditional_edges(
        NODE_RISK,
        review_router,
        {NODE_REVIEW: NODE_REVIEW, NODE_REPORT: NODE_REPORT, NODE_ERROR: NODE_ERROR},
    )

    # Human review always proceeds to report writing.
    graph.add_edge(NODE_REVIEW, NODE_REPORT)

    # Error handler -> best-effort report or straight to final summary.
    graph.add_conditional_edges(
        NODE_ERROR,
        error_handler_router,
        {NODE_REPORT: NODE_REPORT, NODE_FINAL: NODE_FINAL},
    )

    # Report -> final summary -> END.
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
    order = [n for n, _, _ in _BACKBONE] + [NODE_RISK, NODE_REVIEW, NODE_REPORT, NODE_FINAL, NODE_ERROR]
    for i, n in enumerate(order, 1):
        lines.append(f"  {i:2d}. {n}")
    lines += [
        "",
        "Edges:",
        "  START -> input_manager",
        "  <each backbone node> -> next  (or -> error_handler on critical error)",
        "  risk_assessment_agent -> human_review        [if review required]",
        "  risk_assessment_agent -> report_writer_agent [if no review needed]",
        "  human_review -> report_writer_agent",
        "  error_handler -> report_writer_agent [can continue] | final_summary [stop]",
        "  report_writer_agent -> final_summary -> END",
    ]
    return "\n".join(lines)
