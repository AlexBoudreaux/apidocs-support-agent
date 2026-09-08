"""The reviewer's three tools. Build spec section 4.1, RFC 3.6, decisions 9 and 10.

All three are closures over a `ReviewContext`. They mutate the context and return
a short string for the agent to read. The reviewer can look things up and rewrite
the draft. It cannot approve, send, or touch the ticket.

`rerun_retrieval` is a tool and not a graph edge back to the retrieval node
because that is how a review actually goes. The engineer says "go read this doc
and let's write it again", never "start over from scratch". `rewrite_draft` is a
tool and not chat prose because the draft is a state field with its own pane, and
the edit scorer needs two texts to diff.
"""

from __future__ import annotations

import logging

from langchain_core.tools import tool

from app.nodes.draft import write_draft
from app.retrieval.subgraph import run_retrieval
from app.reviewer.agent import ReviewContext

log = logging.getLogger(__name__)


def _render(doc) -> str:
    """One doc as the agent should read it, with the url it must cite verbatim."""
    head = f"{doc['doc_id']}  {doc.get('route') or ''}  [{doc['version']}, {doc['status']}]"
    if doc.get("replaced_by"):
        head += f"  replaced by {doc['replaced_by']}"
    return f"{head}\n\n{doc.get('text', '')}\n\nSource: {doc.get('url', '')}"


def make_reviewer_tools(ctx: ReviewContext) -> list:
    """Build `[fetch_doc_section, rerun_retrieval, rewrite_draft]` over `ctx`."""

    @tool
    def fetch_doc_section(route: str, version: str) -> str:
        """Look up one documentation section by route path and API version.

        The route carries its version prefix, for example
        `/v3/payments/{id}/refund`. Version is `v2` or `v3`.
        """
        docs = ctx.kb.exact(route, version, use_cache=False)
        if not docs:
            return (
                f"no doc for route {route!r} at {version!r}. Check the route path "
                "and whether that route exists in that version."
            )
        log.info("reviewer tool: fetch_doc_section %s %s -> %d doc(s)", route, version, len(docs))
        if len(docs) == 1:
            return _render(docs[0])
        # `(route, version)` is not unique. POST and GET /payments are two docs on
        # one path, same for the webhook endpoints route. Returning one of them
        # silently answers a question about creating a payment with the list doc.
        header = (
            f"{len(docs)} docs share the path {route} at {version}, one per HTTP "
            "method. Both are below. Use the one the ticket is about.\n\n"
        )
        return header + "\n\n---\n\n".join(_render(d) for d in docs)

    @tool
    def rerun_retrieval(hint: str) -> str:
        """Run the documentation search again for this ticket with a hint.

        The hint is what the engineer thinks the search missed, for example
        "look at the v2 deliveries retry doc". This replaces the docs in the
        middle pane.
        """
        result = run_retrieval(ctx.ticket, ctx.kb, ctx.config, hint=hint)
        ctx.relevant_docs = result["relevant_docs"]
        log.info("reviewer tool: rerun_retrieval %r -> %d doc(s)", hint, len(ctx.relevant_docs))
        if not ctx.relevant_docs:
            return "found nothing new. The docs still do not cover this."
        return "Docs now in the pane:\n" + "\n".join(
            f"- {d['doc_id']} {d.get('route') or d.get('error_code') or ''} {d.get('url', '')}"
            for d in ctx.relevant_docs
        )

    @tool
    def rewrite_draft(instruction: str) -> str:
        """Rewrite the draft in the middle pane following one instruction.

        Pass the engineer's instruction as they said it, for example "say backoff
        is v3 only and give the v2 workaround". This is the only way the draft
        changes.
        """
        ctx.draft = write_draft(
            ctx.ticket,
            ctx.relevant_docs,
            "answer",
            instruction=instruction,
            prior_draft=ctx.draft,
        )
        ctx.notes.append(instruction)
        log.info("reviewer tool: rewrite_draft %r -> %d chars", instruction, len(ctx.draft))
        return f"Draft updated. Summary of change: {instruction}"

    return [fetch_doc_section, rerun_retrieval, rewrite_draft]
