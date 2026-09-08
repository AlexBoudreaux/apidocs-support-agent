"""draft and `write_draft`. Build spec sections 4.1 and 9, RFC 3.4.

Reads `ticket`, `relevant_docs`, `disposition`, `guardrail_flags`, `first_draft`.
Writes `draft`, and `first_draft` only if it is None.

`write_draft` is shared by this node and the reviewer's `rewrite_draft` tool so
there is one drafting prompt in one place. That is what makes the answer to
"does the agent write differently from the pipeline" a flat no.

The prompt has the four parts from RFC 3.4, plus two conditional parts. Part 5
is the guardrail flag list on a retry, which is what makes the second attempt a
real fix rather than a coin flip. Part 6 is the reviewer's instruction and the
draft it applies to, which is the rewrite path.

On abstain the whole prompt is swapped for a gap report, which goes to the
reviewer and never to the customer.
"""

from __future__ import annotations

import logging

from langchain_core.runnables import RunnableConfig

from app import settings
from app.state import Doc, Ticket, TicketState

log = logging.getLogger(__name__)


# ---------- prompt parts ----------

# 1. Role and task. 3. Structure and writing rules. 4. Deep link format.
SYSTEM_PROMPT = """\
You draft replies to support tickets for a payments and webhooks API provider. \
The customer is a developer at a bank integrating against the API. A support \
engineer reads your draft, edits it, and sends it. Write what that engineer \
would have written.

Ground rules.
- Cite only the documentation given to you. If the docs do not answer part of \
the question, say that part is not covered rather than filling the gap.
- Never invent a route, a parameter, a field name, an error code, or a url. \
Every route path and every link you write is checked against the provided docs \
by a program before a human sees it, and an invented one is flagged back to you.
- The customer's API version is stated on the ticket. Answer for that version. \
When the behavior differs between v2 and v3 and the difference is the point, say \
so in one sentence.

Structure.
1. The answer in the first sentence. What is happening and what to do.
2. The specific route and version it depends on.
3. A short example from the docs if the docs carry one.
4. The deep links, as `[POST /v3/payments/{id}/refund](url)`, where the url is \
that doc's url copied exactly as given.

Writing rules. No preamble. No greeting and no sign off. Do not thank the \
customer or call it a great question. Do not restate the ticket back to them. \
No hedging. No bulleted list of things they did not ask about. Short sentences. \
Aim for under 250 words.
"""

# The abstain path. Parts 2 and 3 are replaced by the gap report format.
GAP_SYSTEM_PROMPT = """\
You write gap reports for a support engineer at a payments and webhooks API \
provider. The documentation search ran three passes on this ticket and came back \
with nothing that answers it, so there is no answer to draft.

This report goes to the support engineer, never to the customer. Do not write a \
customer reply and do not apologize.

Write four short labelled sections.
- What the customer asked. One or two sentences, in your own words.
- What was searched. The product area and API version the search covered, and \
anything the search did retrieve.
- Why it does not answer. Say plainly what the documentation does not contain.
- What to check next. Concrete suggestions for the engineer, for example a team \
that would know, or a doc set outside this corpus.

Do not invent a route, a url, or an error code. If the search retrieved nothing, \
cite nothing. Under 200 words.
"""

TICKET_BLOCK = """\
Ticket {id}
Tenant: {tenant}
API version: {api_version}
Product area: {product_area}
Subject: {subject}

{body}
"""

NO_DOCS = "No documentation was retrieved for this ticket."


def _docs_block(docs: list[Doc]) -> str:
    """Part 2 of the prompt. The retrieved docs, with the url the draft must copy."""
    if not docs:
        return NO_DOCS
    chunks = []
    for doc in docs:
        header = [f"doc_id: {doc['doc_id']}"]
        if doc.get("route"):
            header.append(f"route: {doc['route']}")
        if doc.get("error_code"):
            header.append(f"error code: {doc['error_code']}")
        header.append(f"version: {doc['version']}")
        header.append(f"status: {doc['status']}")
        if doc.get("replaced_by"):
            header.append(f"replaced by: {doc['replaced_by']}")
        if doc.get("url"):
            header.append(f"url: {doc['url']}")
        if doc.get("source") == "approved_answer":
            header.append("source: a previously approved answer, not the reference docs")
        chunks.append("\n".join(header) + "\n\n" + doc.get("text", ""))
    return "\n\n---\n\n".join(chunks)


def _text_of(response) -> str:
    """Coerce a chat response to plain text.

    `content` is a string on most providers and a list of content blocks on some,
    and the draft is prose either way.
    """
    content = getattr(response, "content", response)
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = [
            block if isinstance(block, str) else block.get("text", "")
            for block in content
        ]
        return "\n".join(p for p in parts if p).strip()
    return str(content).strip()


def write_draft(
    ticket: Ticket,
    docs: list[Doc],
    disposition: str,
    flags: list[str] | None = None,
    instruction: str | None = None,
    prior_draft: str | None = None,
) -> str:
    """Produce the customer-facing text, or the gap report on abstain.

    One `MODEL_STRONG` generation, no structured output, because the draft is
    prose. Called by the draft node and by the reviewer's `rewrite_draft` tool.
    """
    abstain = disposition == "abstain"
    system = GAP_SYSTEM_PROMPT if abstain else SYSTEM_PROMPT

    human = [TICKET_BLOCK.format(**ticket)]
    if abstain:
        human.append(
            "Documentation search covered the "
            f"{ticket['product_area']} area at {ticket['api_version']} across three "
            "passes and kept nothing.\n\n" + _docs_block(docs)
        )
    else:
        human.append("Documentation retrieved for this ticket:\n\n" + _docs_block(docs))

    # Part 5. The guardrail retry. The flags are the reason the first attempt was
    # rejected, so the second attempt is a correction and not a reroll.
    if flags:
        human.append(
            "Your previous draft was rejected by an automated check for these "
            "reasons. Fix every one of them. Anything named here that is not in "
            "the documentation above must be removed or replaced with something "
            "that is.\n"
            + "\n".join(f"- {flag}" for flag in flags)
        )

    # Part 6. The rewrite path. The reviewer is a support engineer looking at the
    # draft next to the docs, so their instruction outranks the default shape.
    if instruction:
        human.append(
            "A support engineer reviewed the draft below and asked for a change. "
            "Apply their instruction and change nothing else. Keep every fact and "
            "every link that the instruction does not touch. Return the complete "
            "revised draft, not a diff and not a description of what you changed."
            f"\n\nTheir instruction: {instruction}"
            f"\n\nCurrent draft:\n{prior_draft or '(there is no draft yet)'}"
        )

    model = settings.chat_model("strong")
    response = model.invoke([("system", system), ("human", "\n\n".join(human))])
    return _text_of(response)


def draft(state: TicketState, config: RunnableConfig) -> dict:
    """Write the draft, and pin `first_draft` the first time through."""
    try:
        text = write_draft(
            state["ticket"],
            state.get("relevant_docs", []),
            state.get("disposition", "answer"),
            flags=state.get("guardrail_flags") or None,
        )
    except Exception as exc:  # the drafter is the one node allowed to fail soft
        log.exception("draft failed for ticket %s", state["ticket"]["id"])
        return {
            "draft": f"Drafting failed: {exc}",
            "first_draft": state.get("first_draft") or f"Drafting failed: {exc}",
            "priority": "high",
        }

    update: dict = {"draft": text}
    if state.get("first_draft") is None:
        update["first_draft"] = text
    log.info(
        "draft: %d chars for ticket %s, %d doc(s) cited%s",
        len(text),
        state["ticket"]["id"],
        len(state.get("relevant_docs", [])),
        " (retry after flags)" if state.get("guardrail_flags") else "",
    )
    return update
