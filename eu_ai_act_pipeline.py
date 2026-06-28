"""
EU AI Act assessment pipeline.

Architecture
------------
Outer LangGraph StateGraph  = deterministic, auditable orchestration.
                              You control every step + every state update.
Deep Agents                 = powerful nodes for the conversational /
                              generative work (planning, filesystem, skills).

Flow
----
    START -> intake -> assess (assessor deep agent)
                          |
                          v
                       review (adversarial deep agent, structured verdict)
                          |
              +-----------+-----------+
              | approved /            | rejected & retries left
              | out of retries        |
              v                       v
          finalize <----------------- (loop back to assess with feedback)
              |
             END

Persistence (matches your stack)
--------------------------------
PostgresSaver  -> thread/session state   (one thread == one use-case interaction)
PostgresStore  -> cross-thread memory    (StoreBackend route /memories/)
S3             -> final artifacts        (push step in `finalize`)
"""

from __future__ import annotations

import os
from typing import Annotated, Literal, TypedDict

from pydantic import BaseModel, Field

from langchain_core.messages import AnyMessage, HumanMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.store.postgres import PostgresStore

from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, StateBackend, StoreBackend

DB_URI = os.environ["DB_URI"]  # e.g. postgresql://user:pass@host:5432/db
MAX_REVISIONS = 3


# ---------------------------------------------------------------------------
# 1. OUTER GRAPH STATE  — this is what you control explicitly, step by step.
# ---------------------------------------------------------------------------
class AssessmentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]  # chat w/ use-case team
    brief: str                                           # the experiment brief
    draft_report: str                                    # produced by assessor
    review_verdict: Literal["approved", "rejected", ""]  # from adversarial agent
    review_feedback: str                                 # critique fed back on revise
    revision_count: int                                  # guard vs infinite loops
    final_report: str


# Adversarial reviewer returns *structured* output, not free text — more
# defensible and removes brittle JSON parsing.
class ReviewVerdict(BaseModel):
    verdict: Literal["approved", "rejected"]
    feedback: str = Field(
        default="", description="Specific flaws to fix; empty when approved."
    )


# ---------------------------------------------------------------------------
# 2. THE DEEP AGENTS  — each is a CompiledStateGraph, invoked inside a node.
# ---------------------------------------------------------------------------
def build_backend() -> CompositeBackend:
    """Ephemeral working files in state; durable stuff under /memories/."""
    return CompositeBackend(
        default=StateBackend(),
        routes={"/memories/": StoreBackend()},  # resolves the outer graph's store
    )


ASSESSOR_PROMPT = """You are an EU AI Act compliance analyst.

Use the `eu-ai-act` skill for the classification rules and article references.
Follow these stages and keep a todo list of them:
  1. Read the brief from /workspace/brief.md
  2. Screen for prohibited practices (Article 5).
  3. Check high-risk categories (Annex III).
  4. Check transparency (Article 50) and GPAI obligations.
  5. Assign an overall classification and justify it, citing specific articles.
  6. Write the full assessment to /workspace/report.md.

If the brief is ambiguous on a point that changes the classification, state the
assumption you made explicitly in the report rather than guessing silently."""

assessor = create_deep_agent(
    model="anthropic:claude-sonnet-4-6",
    tools=[],                          # + your retrieval / regulation-lookup tools
    system_prompt=ASSESSOR_PROMPT,
    skills=["./skills/eu-ai-act"],     # SKILL.md, progressive disclosure
    backend=build_backend(),
)

REVIEWER_PROMPT = """You are an adversarial reviewer of EU AI Act assessments.
Your job is to find flaws, not to agree. Be skeptical and specific.

Check for:
  - Annex III categories that were missed or wrongly dismissed.
  - Article 5 (prohibited) concerns waved away without justification.
  - Conclusions not supported by the cited articles.
  - Missing GPAI / transparency obligations.
  - Article citations that don't actually support the stated classification.

Approve only if the assessment is sound and fully justified."""

reviewer = create_deep_agent(
    model="anthropic:claude-sonnet-4-6",
    system_prompt=REVIEWER_PROMPT,
    skills=["./skills/eu-ai-act"],
    backend=build_backend(),
    response_format=ReviewVerdict,     # -> result["structured_response"]
)


# ---------------------------------------------------------------------------
# 3. NODES  — you decide exactly what happens and what state changes at each.
# ---------------------------------------------------------------------------
def intake(state: AssessmentState) -> dict:
    """Pull the brief out of the conversation into a dedicated field; reset loop."""
    brief = state.get("brief") or state["messages"][-1].content
    return {"brief": brief, "revision_count": 0, "review_feedback": ""}


def assess(state: AssessmentState) -> dict:
    """Run the assessor deep agent. Seed its virtual filesystem with the brief;
    on a revision pass, hand it the reviewer's feedback to address."""
    instruction = (
        "Assess this AI use case against the EU AI Act.\n\n"
        f"BRIEF:\n{state['brief']}"
    )
    if state.get("review_feedback"):
        instruction += f"\n\nADDRESS THIS REVIEWER FEEDBACK:\n{state['review_feedback']}"

    result = assessor.invoke(
        {
            "messages": [HumanMessage(instruction)],
            "files": {"/workspace/brief.md": state["brief"]},  # seed the FS
        }
    )

    report = result["files"].get("/workspace/report.md", "")
    return {
        "draft_report": report,
        "messages": result["messages"],  # surface agent reasoning to the UI
    }


def review(state: AssessmentState) -> dict:
    """Adversarial agent critiques the draft and returns a structured verdict."""
    result = reviewer.invoke(
        {
            "messages": [
                HumanMessage(
                    "Critically review this EU AI Act assessment:\n\n"
                    f"{state['draft_report']}"
                )
            ],
            "files": {"/workspace/report.md": state["draft_report"]},
        }
    )
    verdict: ReviewVerdict = result["structured_response"]
    return {
        "review_verdict": verdict.verdict,
        "review_feedback": verdict.feedback,
        "revision_count": state["revision_count"] + 1,
    }


def finalize(state: AssessmentState) -> dict:
    """Approved (or out of retries): persist the final artifact to AWS."""
    report = state["draft_report"]
    # push_to_s3(report, bucket="...", key=f"assessments/{thread}/report.md")
    return {"final_report": report}


# ---------------------------------------------------------------------------
# 4. CONTROL FLOW  — the adversarial loop with a hard retry ceiling.
# ---------------------------------------------------------------------------
def route_after_review(state: AssessmentState) -> Literal["revise", "finalize"]:
    if state["review_verdict"] == "approved":
        return "finalize"
    if state["revision_count"] >= MAX_REVISIONS:
        return "finalize"  # ship with caveat, or route to a human_escalation node
    return "revise"


# ---------------------------------------------------------------------------
# 5. ASSEMBLE & COMPILE  — checkpointer + store = session / thread management.
# ---------------------------------------------------------------------------
def build_graph(checkpointer, store):
    builder = StateGraph(AssessmentState)
    builder.add_node("intake", intake)
    builder.add_node("assess", assess)
    builder.add_node("review", review)
    builder.add_node("finalize", finalize)

    builder.add_edge(START, "intake")
    builder.add_edge("intake", "assess")
    builder.add_edge("assess", "review")
    builder.add_conditional_edges(
        "review",
        route_after_review,
        {"revise": "assess", "finalize": "finalize"},
    )
    builder.add_edge("finalize", END)

    return builder.compile(checkpointer=checkpointer, store=store)


if __name__ == "__main__":
    with PostgresStore.from_conn_string(DB_URI) as store, \
         PostgresSaver.from_conn_string(DB_URI) as checkpointer:
        store.setup()
        checkpointer.setup()

        graph = build_graph(checkpointer, store)

        # one thread == one use-case interaction; the UI reuses this thread_id
        config = {"configurable": {"thread_id": "usecase-1234"}}
        final_state = graph.invoke(
            {"messages": [HumanMessage("Here is our experiment brief: ...")]},
            config,
        )
        print(final_state["final_report"])
