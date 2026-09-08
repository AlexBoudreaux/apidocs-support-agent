"""triage and its router. Build spec section 4.1, RFC 3.2.

Reads `ticket`. Writes `disposition`, `triage_reason`, and `priority` (high on
escalate).

One `MODEL_FAST` call with `TriageDecision`. This is the only place the system
decides not to look at the documentation at all, so the prompt is narrow: it
lists what escalate means in this domain and tells the model to pick `answer`
whenever it is unsure. Retrieval catches the case where the docs do not help,
and the human sees every ticket either way, so the cost of guessing `answer`
wrongly is one wasted retrieval pass, while the cost of guessing `escalate`
wrongly is a customer who never gets an answer.
"""

from __future__ import annotations

import logging

from langchain_core.runnables import RunnableConfig

from app import settings
from app.state import TicketState, TriageDecision

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You triage inbound support tickets for a payments and webhooks API provider. \
The customers are developers at banks integrating against the API.

Decide one thing. Is this a question that can be answered from the API \
documentation, or does it need a human for a reason that has nothing to do with \
the docs?

Escalate only when the ticket needs *you*, the provider, to act on the \
customer's account. Do not escalate a ticket that asks how something works or \
which call to make. The test is who has to do something next, not how urgent \
or how commercial the ticket sounds.

Return `escalate` when the ticket asks you to do something the customer cannot \
do through the API themselves:
- a dispute with you, a threat to sue, a regulator, a contract being invoked
- money on your invoice to move: a credit, a corrected invoice, a refund of the \
customer's own subscription
- the account itself to change: provisioning, adding or removing users, a \
credential rotated or revoked
- a live security incident, a suspected breach, a leaked credential the \
customer wants killed
- something only a person can give: a sales conversation, a complaint about \
support itself

Return `answer` for every ticket that is asking a question, including these:
- it asks how to do something, or which route to call, however urgent the \
underlying situation is and however forcefully the customer states what they \
want to happen. They are asking you for the instruction, not for the action.
- it asks what something costs, what commitments exist, or where or how the \
platform does something. Asking about a commercial or legal subject is a \
question. Only demanding something under one is a dispute.
- it asks you to look into why the API responded the way it did, including \
when the customer guesses their account or key is at fault. Explaining an API \
response is a documentation question.
- the dispute in it is between the customer and their own customer, not with \
you.
- you doubt the documentation covers it at all.

Later steps search the documentation and refuse on their own when it does not \
cover the subject, and a human reviews every ticket regardless. When you are \
unsure, return `answer`. Triage errs toward looking.

`reason` is one sentence, written for the support engineer who will see it \
next to the ticket.
"""

TICKET_TEMPLATE = """\
Ticket {id}
Tenant: {tenant}
API version: {api_version}
Product area: {product_area}
Subject: {subject}

{body}
"""


def triage(state: TicketState, config: RunnableConfig) -> dict:
    """Answer or escalate, before anything is retrieved."""
    ticket = state["ticket"]
    model = settings.chat_model("fast").with_structured_output(TriageDecision)

    try:
        decision: TriageDecision = model.invoke(
            [
                ("system", SYSTEM_PROMPT),
                ("human", TICKET_TEMPLATE.format(**ticket)),
            ]
        )
    except Exception as exc:
        # A ticket that should have been escalated still reaches a human through
        # the normal path, so failing open toward `answer` costs a retrieval pass
        # and nothing else.
        log.exception("triage: model call failed for %s, defaulting to answer", ticket["id"])
        return {
            "disposition": "answer",
            "triage_reason": f"triage model call failed ({exc}), defaulted to answer",
            "priority": "normal",
        }

    log.info(
        "triage: ticket %s -> %s (%s)", ticket["id"], decision.disposition, decision.reason
    )
    return {
        "disposition": decision.disposition,
        "triage_reason": decision.reason,
        "priority": "high" if decision.disposition == "escalate" else "normal",
    }


def route_after_triage(state: TicketState) -> str:
    """Escalate skips retrieval and drafting and goes straight to the human."""
    return "review" if state.get("disposition") == "escalate" else "retrieval"
