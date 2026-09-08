"""State schema, frozen.

Nothing here changes without updating every reader and writer first.
Every field's writers and readers are the trailing comments.
"""

import operator
from typing import Annotated, Literal

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel
from typing_extensions import TypedDict


# ---------- data records ----------

class Ticket(TypedDict):
    id: str
    tenant: str
    api_version: Literal["v2", "v3"]
    product_area: Literal["payments", "webhooks", "unknown"]
    subject: str
    body: str
    created_at: str


class Doc(TypedDict):
    doc_id: str                      # "payments-refund-v3", "payments-errors#PAY_4012", "approved-<ticket_id>"
    source: Literal["doc", "approved_answer"]
    route: str                       # "/v3/payments/{id}/refund", or "" for an error table row
    version: Literal["v2", "v3", "all"]
    area: Literal["payments", "webhooks"]
    status: Literal["current", "deprecated"]
    replaced_by: str | None          # route path, set when status == "deprecated"
    error_code: str | None           # set for error table rows
    description: str                 # one or two sentences, what the semantic index embeds
    url: str                         # the deep link
    text: str                        # full section text


class RetrievalStats(TypedDict):
    iterations: int                  # reflect passes, 1..3
    queries_run: int                 # total Send branches across all passes
    modes: list[Literal["exact", "semantic"]]
    abstained: bool


class SentRecord(TypedDict):
    ticket_id: str
    kind: Literal["answer", "escalation"]
    posted_at: str


class EditScore(TypedDict):
    tier: int                        # 1 for tier 1 result
    kind: Literal["none", "style", "correctness"]
    added_identifiers: list[str]
    removed_identifiers: list[str]
    char_delta: int


# ---------- structured outputs ----------

class TriageDecision(BaseModel):
    disposition: Literal["answer", "escalate"]
    reason: str


class SearchQuery(BaseModel):
    mode: Literal["exact", "semantic"]
    route: str | None = None
    version: Literal["v2", "v3"] | None = None
    error_code: str | None = None
    text: str | None = None


class QueryPlan(BaseModel):
    queries: list[SearchQuery]       # planner prompt says 1 to 3, code truncates to 3


class Reflection(BaseModel):
    decision: Literal["done", "again", "abstain"]
    keep: list[str]                  # doc_ids
    missing: str | None = None


class ReviewDecision(BaseModel):
    action: Literal["approve", "escalate"]
    final_answer: str
    human_tag: Literal["good_as_is", "fixed_wording", "fixed_facts", "added_context", "escalated"]
    save_to_kb: bool = False
    save_to_eval: bool = False
    escalation_note: str | None = None


class CorrectnessVerdict(BaseModel):
    passed: bool
    reason: str


# ---------- graph state ----------

class TicketState(TypedDict):
    ticket: Ticket                                         # intake writes. all read
    first_trace_id: str | None                             # intake writes once. post_send reads
    disposition: Literal["answer", "abstain", "escalate"]  # triage writes; retrieval wrapper overwrites to abstain
    triage_reason: str | None                              # triage writes. review UI reads
    relevant_docs: list[Doc]                               # retrieval wrapper writes; rerun_retrieval tool overwrites
    retrieval_stats: RetrievalStats | None                 # retrieval wrapper writes. evals and UI read
    first_draft: str | None                                # draft node writes once, never overwritten
    draft: str | None                                      # draft node writes; rewrite tool overwrites
    guardrail_flags: list[str]                             # guardrail and send write. draft reads on retry
    guardrail_attempts: int                                # guardrail increments. edge reads. max 2
    priority: Literal["normal", "high"]                    # triage, retrieval wrapper, guardrail write. UI sorts
    messages: Annotated[list[AnyMessage], add_messages]    # review and reviewer_agent append
    pending_human: str | None                              # review writes one chat message; reviewer_agent consumes and clears
    review: ReviewDecision | None                          # review writes on decision
    sent: SentRecord | None                                # send writes
    edit_score: EditScore | None                           # post_send writes


class RetrievalState(TypedDict):
    ticket: Ticket
    hint: str | None                                       # reviewer's hint on rerun, None from the pipeline
    missing: str | None                                    # reflect writes on again
    queries: list[SearchQuery]                             # planner writes
    results: Annotated[list[Doc], operator.add]            # each search branch appends
    iteration: int                                         # planner increments
    decision: Literal["done", "again", "abstain"] | None   # reflect writes
    keep: list[str]                                        # reflect writes
    modes: Annotated[list[str], operator.add]              # each search branch appends its mode
