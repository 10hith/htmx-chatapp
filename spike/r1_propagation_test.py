"""
R1 plumbing test WITHOUT an OpenAI key.

Question: when an LLM runs inside an outer-graph node (via a compiled child graph),
do its token chunks surface to the OUTER `graph.astream(stream_mode=["messages"],
subgraphs=True)` with metadata pointing into the child node?

We use a fake streaming chat model. This proves the LangGraph propagation plumbing
(not deepagents-specific behavior, which needs the real key). Two attempts:
  A) real deepagents deep agent built on the fake model;
  B) if that needs a tool-capable model, a plain child StateGraph with one LLM node.
"""

from __future__ import annotations

import asyncio
from typing import Annotated, TypedDict

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langgraph.graph import START, END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import InMemorySaver


def make_fake():
    # GenericFakeChatModel streams its message content chunk-by-chunk.
    return GenericFakeChatModel(
        messages=iter([AIMessage("Kyoto: day 1 Fushimi Inari, day 2 Arashiyama, day 3 Gion.")])
    )


class S(TypedDict):
    messages: Annotated[list, add_messages]


async def run_outer(plan_node):
    b = StateGraph(S)
    b.add_node("plan", plan_node)
    b.add_edge(START, "plan")
    b.add_edge("plan", END)
    g = b.compile(checkpointer=InMemorySaver())

    seen = []
    async for ns, mode, payload in g.astream(
        {"messages": [("user", "plan kyoto")]},
        {"configurable": {"thread_id": "t1"}},
        stream_mode=["messages", "updates"],
        subgraphs=True,
    ):
        if mode == "messages":
            chunk, meta = payload
            content = getattr(chunk, "content", "")
            if content:
                seen.append((ns, meta.get("langgraph_node"), content))
    return seen


async def attempt_deepagent():
    from deepagents import create_deep_agent
    from deepagents.backends import CompositeBackend, StateBackend, StoreBackend

    agent = create_deep_agent(
        model=make_fake(),
        tools=[],
        system_prompt="plan trips",
        backend=CompositeBackend(default=StateBackend(), routes={"/memories/": StoreBackend()}),
    )

    async def plan(state: S):
        res = await agent.ainvoke({"messages": state["messages"]})
        return {"messages": res["messages"][-1:]}

    return await run_outer(plan)


async def attempt_plain_subgraph():
    """Child StateGraph with a single LLM node invoked inside the outer node."""
    fake = make_fake()

    class CS(TypedDict):
        messages: Annotated[list, add_messages]

    async def llm_node(state: CS):
        out = await fake.ainvoke(state["messages"])
        return {"messages": [out]}

    cb = StateGraph(CS)
    cb.add_node("llm_node", llm_node)
    cb.add_edge(START, "llm_node")
    cb.add_edge("llm_node", END)
    child = cb.compile()

    async def plan(state: S):
        res = await child.ainvoke({"messages": state["messages"]})
        return {"messages": res["messages"][-1:]}

    return await run_outer(plan)


async def main():
    for label, fn in (("deepagent+fake", attempt_deepagent), ("plain-subgraph+fake", attempt_plain_subgraph)):
        try:
            seen = await fn()
            print(f"\n=== {label}: {len(seen)} message-mode chunks ===")
            for s in seen[:12]:
                print("  ns=", s[0], "node=", s[1], "content=", repr(s[2])[:50])
            if seen:
                print(f"  >> PROPAGATION WORKS for {label}: inner tokens reached outer messages-mode")
        except Exception as e:
            print(f"\n=== {label}: FAILED -> {type(e).__name__}: {str(e)[:160]}")


if __name__ == "__main__":
    asyncio.run(main())
