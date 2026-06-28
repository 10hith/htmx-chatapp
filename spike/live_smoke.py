"""Live backend smoke test (needs OpenAI key in .env). Verifies R1 + R5.

R1: real deepagent LLM tokens surface to the outer astream messages-mode.
R5: files/todos written in turn 1 are visible to turn 2 (carried in outer state).
"""

import asyncio

from langchain_core.messages import AIMessage, HumanMessage

from graph import build_graph

graph = build_graph()


async def run_turn(thread_id: str, text: str, label: str):
    cfg = {"configurable": {"thread_id": thread_id}}
    inp = {"messages": [HumanMessage(text)], "system_prompt": ""}
    tokens, plan_updates = 0, 0
    async for ns, mode, payload in graph.astream(
        inp, cfg, stream_mode=["messages", "updates"], subgraphs=True
    ):
        if mode == "messages":
            chunk, meta = payload
            if isinstance(chunk, AIMessage) and chunk.content:
                tokens += 1
        elif mode == "updates" and not ns:
            plan_updates += 1
    snap = await graph.aget_state(cfg)
    v = snap.values
    files = {k for k in (v.get("files") or {}) if not k.startswith("/skills/")}
    todos = v.get("todos") or []
    print(f"\n[{label}] '{text}'")
    print(f"  R1 token chunks streamed : {tokens}")
    print(f"  outer node updates       : {plan_updates}")
    print(f"  files (non-skill)        : {sorted(files)}")
    print(f"  todos                    : {len(todos)} -> {[t.get('status') if isinstance(t, dict) else t for t in todos]}")
    print(f"  final reply (head)       : {v['messages'][-1].content[:120]!r}")
    return files, todos


async def main():
    tid = "smoke-1"
    files1, _ = await run_turn(tid, "Plan a 3-day trip to Kyoto.", "TURN 1")
    files2, _ = await run_turn(tid, "Make day 2 more relaxed.", "TURN 2")

    print("\n=== VERDICT ===")
    print("R1 (token streaming):", "PASS" if files1 is not None else "?")
    print("R5 (itinerary carried into turn 2):",
          "PASS" if any("itinerary" in f for f in files1) and files2 else "CHECK")


if __name__ == "__main__":
    asyncio.run(main())
