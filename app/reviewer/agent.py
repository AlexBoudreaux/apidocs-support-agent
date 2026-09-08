"""The reviewer agent. Build spec section 4.1, RFC 3.6, decision 2.

This is the "reveal" from the original engagement. The reviewers there stopped
using the system as an answer machine and started using it as a search partner,
going back and forth with it and pointing it at specific sections of the docs.
So the human step is an agent the reviewer talks to, not an approve button.

`create_agent` from the `langchain` package, three tools, `PIIMiddleware`
attached. Not Deep Agents: the filesystem, planner, skills, and subagent
spawning solve problems this reviewer does not have, and the smallest agent that
does the job is the one a bank's security team can read in a glance.

`ReviewContext` is the seam. Tools mutate the context, the node reads the context
back into graph state. Tools never touch graph state directly, which keeps the
agent-to-parent state boundary one-way and inspectable.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from langchain.agents import create_agent
from langchain.agents.middleware import PIIMiddleware
from langchain_core.runnables import RunnableConfig

from app import settings
from app.checks import API_KEY_REGEX
from app.kb.index import KnowledgeBase
from app.state import Doc, Ticket

log = logging.getLogger(__name__)

# Build spec said 10. Measured on 2026-09-04, 10 is not enough for even two tool
# calls, because every middleware hook is its own superstep inside `create_agent`.
# One tool-calling cycle costs 6 steps with the two `PIIMiddleware` instances
# attached: before_model twice, model, after_model twice, tools. A final answer
# turn with no tool call costs 5. So four tool calls plus an answer is 29, and 30
# is the number that means "three or four lookups, then stop". Build spec 4.1
# updated to match.
RECURSION_LIMIT = 30

SYSTEM_PROMPT = """\
You are helping a support engineer finalize a reply to a customer's API support \
ticket. The engineer is looking at three panes. The ticket on the left, the \
draft reply in the middle, and this conversation on the right.

You can do three things.
- `fetch_doc_section(route, version)` looks up one documentation section by its \
route path and API version. Route paths carry their version prefix, for example \
`/v3/payments/{id}/refund`.
- `rerun_retrieval(hint)` runs the documentation search again for this ticket \
with a hint from the engineer, and replaces the retrieved docs.
- `rewrite_draft(instruction)` rewrites the draft in the middle pane. This is the \
only way the draft changes. Never paste a rewritten draft into the chat, call \
the tool instead.

You cannot approve, send, or escalate. Those stay with the engineer.

Keep chat replies short, two or three sentences. The draft lives in its own \
pane, so the reply is where you say what you found or what you changed, not \
where you restate the draft. When you looked something up, say what the doc \
actually said. Never invent a route, a parameter, an error code, or a url.
"""

CONTEXT_TEMPLATE = """\
Ticket {id}
Tenant: {tenant}
API version: {api_version}
Product area: {product_area}
Subject: {subject}

{body}

---

Current draft:
{draft}

---

Docs retrieved so far:
{docs}
"""


@dataclass
class ReviewContext:
    """One reviewer turn's mutable scratch space."""

    ticket: Ticket
    draft: str | None
    relevant_docs: list[Doc]
    kb: KnowledgeBase
    config: RunnableConfig
    notes: list[str] = field(default_factory=list)


def _docs_summary(docs: list[Doc]) -> str:
    """One line per doc. The agent fetches the full text when it needs it."""
    if not docs:
        return "(nothing retrieved)"
    return "\n".join(
        f"- {d['doc_id']} {d.get('route') or d.get('error_code') or ''} "
        f"[{d['version']}, {d['status']}] {d.get('url', '')}"
        for d in docs
    )


def build_reviewer_agent(ctx: ReviewContext) -> Any:
    """Build the agent for one turn, with its tools closed over `ctx`.

    Built per turn rather than once per process because the ticket, the draft,
    and the retrieved docs go into the system prompt, and all three change
    between turns. The model call is what costs time here, not the construction.
    """
    # Imported here rather than at module scope: `tools` imports `write_draft`
    # and `run_retrieval`, which import this module for `ReviewContext`.
    from app.reviewer.tools import make_reviewer_tools

    context = CONTEXT_TEMPLATE.format(
        **ctx.ticket,
        draft=ctx.draft or "(no draft, this ticket was escalated before drafting)",
        docs=_docs_summary(ctx.relevant_docs),
    )

    return create_agent(
        # `use_responses_api` is not decoration. `MODEL_FAST` is configured with a
        # reasoning effort, and OpenAI rejects function tools plus a reasoning
        # effort on /v1/chat/completions with "Function tools with
        # reasoning_effort are not supported for <model> in
        # /v1/chat/completions". The alternative is dropping the effort to
        # "none", which throws away a setting Alex chose. This is the only place
        # in the project that binds tools, so the flag lives here and not in
        # settings, where it would change how 4c and 4e call models.
        model=settings.chat_model("fast", use_responses_api=True),
        tools=make_reviewer_tools(ctx),
        system_prompt=f"{SYSTEM_PROMPT}\n---\n\n{context}",
        middleware=[
            # Emails the engineer pastes in, and anything a doc happens to carry.
            PIIMiddleware(
                "email",
                strategy="redact",
                apply_to_input=True,
                apply_to_output=True,
            ),
            # The realistic leak is a bank developer pasting a live key into the
            # ticket. Intake already redacts the ticket, this catches the paste
            # into the chat and anything a tool result drags back in.
            PIIMiddleware(
                "api_key",
                detector=API_KEY_REGEX,
                strategy="redact",
                apply_to_input=True,
                apply_to_output=True,
                apply_to_tool_results=True,
            ),
        ],
    )
