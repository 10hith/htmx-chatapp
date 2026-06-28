"""
Trip Planner deep agent.

A `deepagents` deep agent invoked inside the outer LangGraph `plan` node. The
agent encapsulates its own tool loop (write_todos + filesystem tools). We rebuild
it per request so the editable system prompt takes effect (deepagents bakes
`system_prompt` at construction).

Skill loading note (deepagents 0.6.12): with a `StateBackend` default, `skills=`
paths are resolved against the BACKEND filesystem, not local disk. So we read
`skills/trip-planner/SKILL.md` from disk once and seed it into the agent's virtual
filesystem at `/skills/trip-planner/SKILL.md` on every invoke (see SKILL_FILES).
"""

from __future__ import annotations

from pathlib import Path

from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, StateBackend, StoreBackend
from deepagents.backends.state import create_file_data, file_data_to_string

from config import llm_settings

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SKILL_SRC = _PROJECT_ROOT / "skills" / "trip-planner" / "SKILL.md"

# Backend path the SkillsMiddleware will list (sources=["/skills/trip-planner"]).
# StateBackend stores files as FileData dicts (not raw strings), so seed via
# create_file_data; read back for display via file_text().
SKILL_BACKEND_PATH = "/skills/trip-planner/SKILL.md"
SKILL_FILES: dict[str, dict] = {SKILL_BACKEND_PATH: create_file_data(_SKILL_SRC.read_text())}


def file_text(file_data) -> str:
    """Render a StateBackend FileData entry (or raw string) as text for display."""
    if isinstance(file_data, dict):
        return file_data_to_string(file_data)
    return str(file_data)

DEFAULT_SYSTEM_PROMPT = """You are an upbeat, practical trip planner.

You have a `trip-planner` skill — read it for the workflow, itinerary format, and
conventions, and follow it. Specifically:
- Use `write_todos` to lay out your planning stages and tick them off as you go.
- Write the full day-by-day itinerary to `/workspace/itinerary.md`.
- Save the user's preferences and chosen destinations to `/memories/preferences.md`.
- Keep your chat reply concise — end with a one-line summary; the full plan lives
  in the itinerary file.

If a follow-up asks to change the plan, update the existing files rather than
starting from scratch."""


def build_trip_planner(system_prompt: str | None = None):
    """Construct the trip-planner deep agent with the current system prompt.

    The outer graph supplies the checkpointer + store, so we don't pass them here;
    the `/memories/` StoreBackend resolves the outer graph's store at run time.
    """
    return create_deep_agent(
        model=llm_settings.llm_client,
        tools=[],
        system_prompt=system_prompt or DEFAULT_SYSTEM_PROMPT,
        skills=["/skills/trip-planner"],
        backend=CompositeBackend(
            default=StateBackend(),
            # Static namespace: /memories/ is shared across threads (demo scope).
            routes={"/memories/": StoreBackend(namespace=lambda ctx: ("memories",))},
        ),
    )
