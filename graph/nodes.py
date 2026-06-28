from __future__ import annotations

from deepagent.trip_planner import DEFAULT_SYSTEM_PROMPT, SKILL_FILES, build_trip_planner
from graph.state import AgentState


async def intake(state: AgentState) -> dict:
    """Ensure a system prompt is set for this turn (passes through otherwise)."""
    return {"system_prompt": state.get("system_prompt") or DEFAULT_SYSTEM_PROMPT}


def _carry_files(files: dict) -> dict:
    """Files to carry to the next turn — exclude seeded skill files."""
    return {k: v for k, v in (files or {}).items() if not k.startswith("/skills/")}


async def plan(state: AgentState) -> dict:
    """Run the trip-planner deep agent, then lift its outputs into outer state.

    The agent is rebuilt with the current (editable) system prompt. We seed the
    skill files + the files carried from prior turns, then persist only the final
    AI message (clean chat history) plus the updated files/todos.
    """
    agent = build_trip_planner(state.get("system_prompt") or DEFAULT_SYSTEM_PROMPT)

    seeded_files = {**SKILL_FILES, **(state.get("files") or {})}
    result = await agent.ainvoke(
        {
            "messages": state["messages"],
            "files": seeded_files,
            "todos": state.get("todos") or [],
        }
    )

    final_message = result["messages"][-1]
    return {
        "messages": [final_message],
        "files": _carry_files(result.get("files", {})),
        "todos": result.get("todos", []) or [],
    }
