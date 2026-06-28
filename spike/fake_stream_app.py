"""
R2 spike — no LLM key needed.

Goal: prove the htmx-4 SSE topology for a chat app BEFORE building the real UI:
  1. Per-turn SSE: POST /send returns a fresh assistant bubble that opens its OWN
     SSE connection to GET /stream; tokens stream into THAT bubble.
  2. Right panel (OUTSIDE the bubble) is updated via an OOB swap embedded in a
     `state_update` SSE event -> routed through a hidden `sse-swap="state_update"`
     sink. This is the open question: does htmx-4 honor hx-swap-oob inside
     SSE-swapped content? If #panel updates, topology (a) works.
  3. sse-close="done" must stop EventSource auto-reconnect (no re-run).

Run:  uvicorn spike.fake_stream_app:app --reload --port 8100
"""

from __future__ import annotations

import asyncio
import itertools
from pathlib import Path

from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse
from sse_starlette.sse import EventSourceResponse

app = FastAPI(title="R2 SSE spike")

_gen_counter = itertools.count(1)
HERE = Path(__file__).parent


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    return (HERE / "index.html").read_text()


@app.post("/send", response_class=HTMLResponse)
async def send(message: str = Form(...)) -> str:
    """Return the user bubble + a fresh assistant bubble that opens its own SSE."""
    gen = next(_gen_counter)
    return f"""
    <div class="msg user">🧑 {message}</div>
    <div class="msg ai"
         sse-connect="/stream?gen={gen}"
         sse-close="done">
        <span sse-swap="token" hx-swap="beforeend scroll:bottom"></span>
        <!-- hidden sink: receives state_update events; its payload carries an OOB
             swap that should patch #panel which lives OUTSIDE this bubble -->
        <span sse-swap="state_update" hidden></span>
    </div>
    """


@app.get("/stream")
async def stream(gen: int = 0):
    """Fake token stream + two state_update (OOB) events, then a terminal done."""
    words = ("Planning ", "a ", "3-day ", "trip ", "to ", "Kyoto: ", "day 1 ",
             "Fushimi ", "Inari, ", "day 2 ", "Arashiyama, ", "day 3 ", "Gion. ")

    async def gen_events():
        for i, w in enumerate(words):
            yield {"event": "token", "data": f"<span>{w}</span>"}
            if i == 3:
                # mid-run panel update via OOB embedded in the event payload
                yield {
                    "event": "state_update",
                    "data": '<div id="panel" hx-swap-oob="innerHTML">'
                            '⏳ node=plan · todos: [research ▢] · files: itinerary.md (draft)'
                            "</div>",
                }
            await asyncio.sleep(0.12)
        # final panel update
        yield {
            "event": "state_update",
            "data": '<div id="panel" hx-swap-oob="innerHTML">'
                    '✅ node=plan DONE · todos: [research ✓, itinerary ✓] · '
                    "files: /workspace/itinerary.md</div>",
        }
        # terminal event: client has sse-close="done" -> closes, no reconnect
        yield {"event": "done", "data": "ok"}

    return EventSourceResponse(gen_events())
