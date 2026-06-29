"""
FastAPI app: HTMX chat over SSE, driving a LangGraph + deepagents trip planner.

Flow (SSE is GET-only, so two steps):
  POST /chat/{id}/send   -> record the turn in PENDING, return user + assistant bubbles
  GET  /chat/{id}/stream -> run the graph, stream `token` + `state_update`, end `done`

Run a SINGLE worker (in-memory checkpointer/store/PENDING are per-process):
  uvicorn main:app --reload
"""

from __future__ import annotations

import uuid
from html import escape

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from langchain_core.messages import AIMessage, HumanMessage
from sse_starlette.sse import EventSourceResponse

from deepagent import DEFAULT_SYSTEM_PROMPT, file_text
from graph import build_graph
from render import SPINNER_HTML, sanitize_html, split_message

app = FastAPI(title="Trip Planner Deep-Agent Chat")
templates = Jinja2Templates(directory="templates")
graph = build_graph()

# gen_id -> pending turn. Per-process; fine for a single-worker demo.
PENDING: dict[str, dict] = {}


def _cfg(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


def _chunk_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):  # some providers return content parts
        return "".join(
            p.get("text", "") if isinstance(p, dict) else str(p) for p in content
        )
    return str(content)


def _panel_files(values: dict) -> dict[str, str]:
    out = {}
    for k, v in (values.get("files") or {}).items():
        if k.startswith("/skills/"):
            continue
        text = file_text(v)
        out[k] = sanitize_html(text) if k.endswith(".html") else text
    return out


async def _panel_context(thread_id: str, node: str) -> dict:
    """Authoritative panel data from the committed checkpoint."""
    snap = await graph.aget_state(_cfg(thread_id))
    values = snap.values if snap else {}
    files = _panel_files(values)
    return {
        "msg_count": len(values.get("messages", []) or []),
        "system_prompt": values.get("system_prompt") or DEFAULT_SYSTEM_PROMPT,
        "files": files,
        "todos": values.get("todos") or [],
        "node": node,
        "oob": True,
    }


@app.get("/", include_in_schema=False)
async def root():
    """Generate a new thread and redirect to its chat page."""
    return RedirectResponse(f"/chat/{uuid.uuid4().hex}", status_code=303)


@app.get("/chat/{thread_id}", response_class=HTMLResponse)
async def chat_page(request: Request, thread_id: str):
    """Render the chat SPA. Hydrates full message history and right-panel state
    from the LangGraph checkpoint — no client-side fetch needed on load."""
    snap = await graph.aget_state(_cfg(thread_id))
    values = snap.values if snap else {}
    history = []
    for m in values.get("messages", []) or []:
        if m.type == "human" and m.content:
            history.append({"role": "user", "content": _chunk_text(m.content)})
        elif m.type == "ai" and m.content:
            prose, raw = split_message(_chunk_text(m.content))
            history.append(
                {"role": "ai", "prose": prose, "card_html": sanitize_html(raw) if raw else ""}
            )
    files = _panel_files(values)
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "thread_id": thread_id,
            "history": history,
            "system_prompt": values.get("system_prompt") or DEFAULT_SYSTEM_PROMPT,
            "files": files,
            "todos": values.get("todos") or [],
            "msg_count": len(values.get("messages", []) or []),
            "node": None,
        },
    )


@app.post("/chat/{thread_id}/send", response_class=HTMLResponse)
async def send(
    request: Request,
    thread_id: str,
    message: str = Form(...),
    system_prompt: str = Form(""),
):
    """Record the user turn and return HTML fragments (user bubble + empty
    assistant bubble). The assistant bubble opens its own SSE connection to
    `/stream?gen=` to run the graph — SSE requires GET, so streaming is split."""
    gen = uuid.uuid4().hex
    PENDING[gen] = {"message": message, "system_prompt": system_prompt.strip()}
    return templates.TemplateResponse(
        request,
        "_turn.html",
        {"thread_id": thread_id, "gen": gen, "message": message},
    )


@app.get("/chat/{thread_id}/stream")
async def stream(thread_id: str, gen: str):
    """SSE stream for a single assistant turn. Emits:
    - `token` — incremental text chunks from the deep agent
    - `state_update` — right-panel HTML (OOB swap) after each outer node
    - `done` — signals the client to close the EventSource

    `gen` is a one-time key issued by `/send`; unknown or replayed keys close immediately."""
    pending = PENDING.pop(gen, None)

    async def events():
        # Stray reconnect / unknown gen: close immediately, never re-run the graph.
        if pending is None:
            yield {"event": "done", "data": "ok"}
            return

        inp = {
            "messages": [HumanMessage(pending["message"])],
            "system_prompt": pending["system_prompt"] or DEFAULT_SYSTEM_PROMPT,
        }
        acc, emitted, fence_found = "", 0, False
        async for namespace, mode, payload in graph.astream(
            inp, _cfg(thread_id), stream_mode=["messages", "updates"], subgraphs=True
        ):
            if mode == "messages":
                chunk, _meta = payload
                if isinstance(chunk, AIMessage):
                    text = _chunk_text(chunk.content)
                    if text:
                        acc += text
                        if not fence_found:
                            idx = acc.find("```")
                            if idx == -1:
                                safe = len(acc) - 2
                                if safe > emitted:
                                    yield {
                                        "event": "token",
                                        "data": escape(acc[emitted:safe]),
                                    }
                                    emitted = safe
                            else:
                                if idx > emitted:
                                    yield {
                                        "event": "token",
                                        "data": escape(acc[emitted:idx].rstrip("\n")),
                                    }
                                    emitted = idx
                                fence_found = True
                                yield {"event": "render", "data": SPINNER_HTML}
            elif mode == "updates" and not namespace:
                # An OUTER node completed -> refresh the right panel.
                for node_name in payload:
                    ctx = await _panel_context(thread_id, node_name)
                    html = templates.env.get_template("_panels.html").render(ctx)
                    yield {"event": "state_update", "data": html}

        if not fence_found:
            if emitted < len(acc):
                yield {"event": "token", "data": escape(acc[emitted:])}
        else:
            _, raw = split_message(acc)
            card = sanitize_html(raw) if raw else ""
            yield {"event": "render", "data": card or "<span></span>"}
        yield {"event": "done", "data": "ok"}

    return EventSourceResponse(events())
