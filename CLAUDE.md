# htmx-chatapp

Demo chat SPA: HTMX 2.0.10 + FastAPI + LangGraph + deepagents (Trip Planner skill).

## Running

```bash
uv run uvicorn main:app --reload   # single worker only — see below
```

Requires `.env` (see `.env.example`):
```
llm_model=gpt-4o-mini
llm_openai_api_key=sk-...
```

Open `http://localhost:8000` → redirects to `/chat/{thread_id}`.

## Architecture

```
GET / → redirect to /chat/{thread_id}
GET /chat/{thread_id}      → render SPA, hydrate history server-side
POST /chat/{thread_id}/send → record turn in PENDING, return user+assistant bubbles
GET /chat/{thread_id}/stream → SSE: run graph, stream token + state_update + done
```

**Outer graph** (`graph/`): `START → intake → plan → END`
- `intake` — ensures system_prompt is set
- `plan` — rebuilds the deep agent with the current system prompt, seeds files, invokes, lifts `files`/`todos`/final-message back into outer `AgentState`

**Deep agent** (`deepagent/trip_planner.py`): `create_deep_agent` with Trip Planner skill, `CompositeBackend(default=StateBackend(), routes={"/memories/": StoreBackend(...)})`. Rebuilt each request so the editable system prompt takes effect immediately.

**Streaming** (`main.py`): `graph.astream(stream_mode=["messages","updates"], subgraphs=True)` — `messages` mode yields token chunks; `updates` mode (outer namespace only) triggers right-panel OOB refresh via `state_update` SSE events.

**Frontend** (`templates/`): `hx-ext="sse"` on `<body>`; per-turn `sse-connect` on the assistant bubble; right panel patched via `hx-swap-oob` payloads carried in `state_update` events; `sse-close="done"` prevents EventSource auto-reconnect.

## Non-obvious constraints

**Single worker only.** `PENDING` dict, `InMemorySaver`, and `InMemoryStore` are per-process. Never run `uvicorn -w 2` or gunicorn multi-worker. Upgrade path is `AsyncPostgresSaver` + `PostgresStore`.

**SSE is GET-only.** EventSource can't POST. The two-step flow (`POST /send` → `GET /stream`) exists because of this, not as a design preference.

**htmx 2.0.10, not 4.** htmx-4-beta4's SSE extension (`hx-sse:connect`) opened zero EventSources in every configuration tested. Pinned to `htmx@2.0.10` + `htmx-ext-sse@2.2.4` with the `sse-connect`/`sse-swap`/`sse-close` attribute names.

**deepagents 0.6.12 — FileData format.** `StateBackend` stores files as `FileData` dicts, not raw strings. Seed with `create_file_data(str)`; read for display with `file_data_to_string(fd)`. Passing raw strings raises `AttributeError: 'str' object has no attribute 'get'`.

**Skills are seeded, not loaded from disk.** `deepagents` resolves `skills=` paths against the backend virtual filesystem, not local disk. `SKILL_FILES` reads `skills/trip-planner/SKILL.md` at startup and seeds it via `invoke(files={...})` on every turn.

**Cross-turn file/todo carry.** The deep agent has no inner checkpointer; `StateBackend` is ephemeral per-invoke. `plan` node extracts `result["files"]` and `result["todos"]` into outer `AgentState` and re-seeds them next turn. Skill files are excluded from carry (filtered in `_carry_files`).

**`StoreBackend` needs explicit namespace.** `StoreBackend(namespace=lambda ctx: ("memories",))` — omitting `namespace` triggers a LangChain deprecation warning slated for removal in 0.7.0.

**Starlette 1.3.x `TemplateResponse`.** Signature is `TemplateResponse(request, name, context)` — `request` is the first positional arg. The old `(name, context_dict)` form raises `TypeError: unhashable type: 'dict'`.

## Project layout

```
main.py                        # FastAPI app, routes, SSE handler
graph/
  state.py                     # AgentState: messages, system_prompt, files, todos
  nodes.py                     # intake, plan (rebuilds deep agent per request)
  builder.py                   # StateGraph + InMemorySaver + InMemoryStore
deepagent/
  trip_planner.py              # build_trip_planner(), SKILL_FILES, file_text()
  __init__.py
config/
  llm_setting.py               # LLMSettings (pydantic-settings), llm_client → ChatOpenAI
skills/trip-planner/SKILL.md   # Trip Planner skill definition
templates/
  index.html                   # SPA shell (htmx 2.0.10, DaisyUI dark, 3-column layout)
  _turn.html                   # per-turn fragment: user bubble + SSE-connected AI bubble
  _panels.html                 # right-panel fragment (oob=True for SSE delivery)
spike/                         # proof-of-concept scripts (not production)
  fake_stream_app.py           # R2: OOB-over-SSE topology verified
  r1_propagation_test.py       # R1: token propagation through subgraph (fake model)
  live_smoke.py                # R1+R5: live two-turn test (542 chunks, files carried)
```

## Dependencies (uv)

```bash
uv sync          # install from uv.lock
uv add <pkg>     # add a dependency
```

`uv.lock` is committed. `package = false` in `pyproject.toml` (application, not library).
