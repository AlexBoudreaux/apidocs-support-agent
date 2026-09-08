"""plan_queries. Owner is session 4c. Build spec section 4.2.

Reads `ticket`, `missing`, `hint`, `iteration`. Writes `queries` and `iteration + 1`.

One `MODEL_FAST` call with `QueryPlan` structured output. This is the "structured
object, not a string" item from the brief's five-things list: because the plan is
`{mode, route, version, error_code, text}`, routing exact against semantic is a
testable decision (`tests/test_planner_routing.py`) rather than a vibe, and the
search node downstream never parses free text.

Three things the code does after the model, not the prompt:

* truncate to `MAX_QUERIES`, because the cost of a pass is the fan-out width,
* fill a missing `version` with the ticket's, because a route without a version
  hits nothing in an index keyed on `(route, version)`,
* demote an `exact` query that names neither a route nor an error code to
  `semantic`, because the search node has nothing to look up otherwise.
"""

from __future__ import annotations

import logging

from langchain_core.runnables import RunnableConfig

from app import settings
from app.state import QueryPlan, RetrievalState, SearchQuery, Ticket

log = logging.getLogger(__name__)

MAX_QUERIES = 3

SYSTEM = """You plan documentation searches for an API support agent.

You are given one customer support ticket and you emit 1 to 3 search queries \
against a knowledge base of API reference docs. The knowledge base covers two \
areas, payments and webhooks, in two API versions, v2 and v3, plus one error \
code table per area.

Two search modes:

- "exact" looks up one thing by name. Use it when the ticket names a route \
(set `route`, e.g. "/v3/payments/{id}/refund") or an error code (set \
`error_code`, e.g. "PAY_4012" or "WHK_4220"). One of the two per query, never \
both. Prefer exact whenever the ticket gives you a name to look up, because it \
is the precise index.
- "semantic" searches descriptions in natural language. Use it when the ticket \
describes a symptom or an outcome and never names the route, e.g. "we get 429s \
in sandbox but not production". Set `text` to the developer's question in your \
own words, not the ticket verbatim.

Rules:

- Set `version` on every query to the ticket's API version unless the ticket \
clearly asks about a different one.
- Emit more than one query only when the ticket genuinely asks about more than \
one thing, or when an exact lookup deserves a semantic backstop. Two is common, \
three is the maximum.
- Never invent a route you were not shown or told. If you are unsure of the \
exact path, use semantic mode and describe it instead.
- Routes in this API carry the version prefix and use {id} for path \
parameters: /v2/payments/{id}/refund, /v3/webhooks/deliveries/{id}/retry."""


def _user_prompt(ticket: Ticket, missing: str | None, hint: str | None) -> str:
    parts = [
        "Ticket",
        f"  api_version: {ticket['api_version']}",
        f"  product_area: {ticket['product_area']}",
        f"  subject: {ticket['subject']}",
        f"  body: {ticket['body']}",
    ]
    if hint:
        # A reviewer typed this in the UI while looking at the draft. It is the
        # most specific signal there is and it outranks the ticket, including
        # the ticket's version: "look at the v2 deliveries retry doc" on a v3
        # ticket means v2, because the reviewer is answering a question the
        # customer did not think to ask.
        parts += [
            "",
            f"A human reviewer is re-running this search and asked for: {hint}",
            "Treat that as an instruction. If it names a route, an error code, "
            "or an API version, search exactly that, even when it disagrees "
            "with the ticket's own version. Spend at least one query on it.",
        ]
    if missing:
        # Pass 2 or 3. The previous pass found something, just not enough.
        parts += [
            "",
            "An earlier search pass ran and was not sufficient. What was still "
            f"missing: {missing}",
            "Plan queries that go after the missing piece. Do not repeat the "
            "earlier searches.",
        ]
    return "\n".join(parts)


def _normalize(queries: list[SearchQuery], ticket: Ticket) -> list[SearchQuery]:
    """Truncate, fill the version, and demote unusable exact queries."""
    out: list[SearchQuery] = []
    for query in queries[:MAX_QUERIES]:
        version = query.version or ticket["api_version"]
        if query.mode == "exact" and not (query.route or query.error_code):
            log.info("planner: exact query named nothing, demoting to semantic")
            out.append(
                SearchQuery(
                    mode="semantic",
                    text=query.text or ticket["subject"],
                    version=version,
                )
            )
            continue
        out.append(
            SearchQuery(
                mode=query.mode,
                route=query.route,
                version=version,
                error_code=query.error_code,
                text=query.text,
            )
        )
    return out


def _fallback(ticket: Ticket, missing: str | None, hint: str | None) -> list[SearchQuery]:
    """One semantic query when the model call failed. Section 4.2."""
    return [
        SearchQuery(
            mode="semantic",
            text=hint or missing or ticket["subject"],
            version=ticket["api_version"],
        )
    ]


def plan_queries(state: RetrievalState, config: RunnableConfig) -> dict:
    """Turn the ticket into 1 to 3 structured `SearchQuery` objects."""
    ticket = state["ticket"]
    missing = state.get("missing")
    hint = state.get("hint")

    try:
        model = settings.chat_model("fast").with_structured_output(QueryPlan)
        plan: QueryPlan = model.invoke(
            [
                ("system", SYSTEM),
                ("human", _user_prompt(ticket, missing, hint)),
            ],
            config,
        )
        queries = _normalize(plan.queries, ticket) or _fallback(ticket, missing, hint)
    except Exception:
        log.exception("planner model call failed, falling back to one semantic query")
        queries = _fallback(ticket, missing, hint)

    log.info(
        "plan_queries pass %d: %s",
        state.get("iteration", 0) + 1,
        [q.model_dump(exclude_none=True) for q in queries],
    )
    return {
        "queries": queries,
        "iteration": state.get("iteration", 0) + 1,
    }
