# DeepAgents + LangGraph — EU AI Act Assessment App

Design notes from a working session on architecting an AI use-case compliance
assessment tool.

## Context / requirement

A front-end app where a use-case team submits an experiment brief (an AI use
case). A chat-driven agent compares it against the EU AI Act and produces an
assessment. Requirements:

- Chat interface driving the conversation (clarifying questions, interaction).
- Artifacts produced: todo list, report, etc.
- Postgres backend for persisting agent memory.
- AWS (S3) for storing files / artifacts.
- A few **skills** the agent must use.
- Session management: one thread == one use-case interaction; user can
  retrieve documents created in that thread.
- **Full control over each step**, explicit state updates, and an
  **adversarial reviewer** agent at the end.

## Key findings

### 1. DeepAgents filesystem is per-backend, not automatically per-thread

The virtual filesystem is pluggable:

- **StateBackend (default):** files live in LangGraph agent state — isolated and
  ephemeral per thread; shared between main agent and subagents; lost when the
  conversation ends.
- **StoreBackend:** persistent, cross-thread, namespace-isolated (LangGraph
  `BaseStore`, e.g. `PostgresStore`).
- **FilesystemBackend:** real directory on disk; all threads sharing `root_dir`
  see the same files (no per-thread isolation).
- **CompositeBackend:** route by path prefix (common production pattern):
  ephemeral scratch in state, durable stuff (e.g. `/memories/`) in the store.

### 2. Todo list is state, not a file

`write_todos` (via `TodoListMiddleware`) stores todos in agent state, keyed by
thread. Separate threads -> separate todo lists (no collision). Within one
thread, subagents share files but return a single final report rather than
concurrently mutating shared state — that design avoids write races. There is no
file locking; for genuinely parallel writers, use **reducers** (last-write-wins
otherwise).

### 3. Session management = standard LangGraph machinery

DeepAgents runs on the LangGraph runtime, so:

- **Checkpointer** (`PostgresSaver` / `AsyncPostgresSaver`) = thread/session
  persistence via `thread_id`.
- **Store** (`PostgresStore` behind `StoreBackend`) = cross-thread persistence.

Both are passed at agent/graph creation. (Note: as of deepagents 0.5.0 the
backend *factory* pattern is deprecated — pass pre-constructed backend
*instances*.)

### 4. Updating state after a tool call (DeepAgents flavour)

Same LangGraph primitive (a tool returning `Command`), with two wrinkles:

- Custom state **must inherit from `DeepAgentState`**, passed via
  `state_schema=`.
- Reads now go through **`ToolRuntime`** (unified interface replacing
  `InjectedState` / `InjectedToolCallId` / `get_runtime()`), hidden from the
  model.
- Writes return `Command(update={...})`, and you **must** include a
  `ToolMessage` (use `runtime.tool_call_id`) or the tool call is left
  unanswered.
- Use `Annotated[..., reducer]` for fields parallel tools may touch.
- **Gotcha:** custom state updates can be **lost when control returns from a
  subagent / nested `create_agent`** to the parent deep agent (subagents have
  isolated state, return only a final report). For values that must survive the
  handoff, persist via the `/memories/` Store route.

## Architecture decision

**DeepAgents as the harness, but the assessment core as an explicit LangGraph
`StateGraph`.**

Why DeepAgents for the shell: todos, report/artifacts (virtual FS), skills
(SKILL.md + progressive disclosure), clarifying-question loop, Postgres memory,
and thread==session all map to built-ins rather than hand-rolled code.

Why an explicit graph for the core: an EU AI Act classification (Art. 5
prohibited / Annex III high-risk / limited / minimal + GPAI) is a legal decision
that must be **deterministic and auditable** — not left to "trust the LLM". You
want final control over each step, explicit state transitions, and an
adversarial reviewer with a bounded revision loop.

Resolution: **outer LangGraph `StateGraph` orchestrates; deep agents are nodes.**
Any `create_deep_agent(...)` returns a `CompiledStateGraph`, so it composes — you
call its `.invoke()` inside an ordinary node and map between outer state and the
agent's `messages` / `files`.

### Practical gotchas for this stack

- **No built-in S3 backend.** Keep working files in state/Store during the run;
  push the *finalised* artifact to S3 in a dedicated end step (cleaner than a
  custom `BackendProtocol` backend).
- **Outer state is separate from each deep agent's state.** Extract what you
  need (`result["files"][...]`) into outer state; agent scratch files don't leak
  into the audit trail unless copied.
- **No inner checkpointer.** The outer `PostgresSaver` captures state after each
  node — resumable/inspectable per thread. Inner checkpointers cause nested
  -thread confusion.
- **Clarifying questions:** use LangGraph `interrupt()` inside the relevant node
  so the pause/resume stays inside the controlled flow.
- **Reviewer uses structured output** (`response_format=PydanticModel` ->
  `result["structured_response"]`) so routing keys off a typed object, not a
  parsed string.

## Reference implementation

See `eu_ai_act_pipeline.py` — outer `StateGraph` with nodes
`intake -> assess -> review -> finalize`, an assessor deep agent, an adversarial
reviewer deep agent with a structured verdict, a bounded revision loop, and
Postgres checkpointer + store wired in.

## Open follow-ups

- `interrupt()`-based clarifying-question handling in the `assess` node.
- `eu-ai-act` SKILL.md structure.
- Async Postgres setup (`AsyncPostgresSaver` + `AsyncPostgresStore`).
