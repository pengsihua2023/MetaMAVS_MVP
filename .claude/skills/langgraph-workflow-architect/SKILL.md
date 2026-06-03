---
name: langgraph-workflow-architect
description: Use this skill when designing, modifying, or debugging LangGraph StateGraph workflows for MetaMAVS.
---

# LangGraph Workflow Architect Skill

When working on MetaMAVS LangGraph code:

- Preserve LangGraph as the core workflow.
- Every node must accept state and return partial state updates.
- Keep routing logic in `metamavs/routing.py`.
- Keep graph construction in `metamavs/graph.py`.
- Do not put large business logic directly in graph construction.
- Add or update tests when changing routing.
- Ensure conditional review routing works.

Required checks:

```bash
pytest tests/test_graph.py tests/test_routing.py
```

Before finishing:

- Confirm graph compiles.
- Confirm END is reachable.
- Confirm error routes are valid.
