from __future__ import annotations

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.store.memory import InMemoryStore

from graph.nodes import intake, plan
from graph.state import AgentState


def build_graph():
    """Compile the outer graph: START -> intake -> plan -> END.

    InMemorySaver = per-thread checkpoint (history + carried files/todos).
    InMemoryStore = cross-thread store backing the deep agent's /memories/ route.
    Both are per-process: run a SINGLE uvicorn worker.
    """
    builder = StateGraph(AgentState)
    builder.add_node("intake", intake)
    builder.add_node("plan", plan)
    builder.add_edge(START, "intake")
    builder.add_edge("intake", "plan")
    builder.add_edge("plan", END)
    return builder.compile(checkpointer=InMemorySaver(), store=InMemoryStore())
