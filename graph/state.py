from __future__ import annotations

from typing import Annotated, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    """Outer graph state — the deterministic part we control.

    `messages` is the user-facing conversation (human + final AI per turn only;
    the deep agent's intermediate tool chatter is not persisted here).
    `files` and `todos` are carried across turns and re-seeded into the deep agent,
    because the deep agent has no inner checkpointer (StateBackend is per-invoke).
    """

    messages: Annotated[list[AnyMessage], add_messages]
    system_prompt: str
    files: dict
    todos: list
