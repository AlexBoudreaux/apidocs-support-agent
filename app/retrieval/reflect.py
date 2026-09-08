"""reflect and its router. Owner is session 4c. Build spec section 4.2.

Reads `ticket`, `results`, `iteration`. Writes `decision`, `keep`, `missing`.

One `MODEL_FAST` call with `Reflection` asking one question over everything
retrieved so far: done with these doc ids, again with a note on what is
missing, or abstain because the docs do not cover this.

Two guarantees live in code, not in the prompt.

* **`keep` is validated against real result ids.** A hallucinated doc id would
  otherwise reach the drafter as a citation with no text behind it.
* **The three-pass cap is the edge.** `route_after_reflect` counts, so no
  prompt wording can loop the subgraph forever. A model that still says "again"
  on the last pass gets its answer rewritten to `abstain` here, which is the
  third exit from the brief: I looked three times and the docs do not cover
  this, so the drafter writes a gap report instead of a fake answer.

`abstain` itself is available on every pass. It used to be gated behind
`MIN_PASSES_BEFORE_ABSTAIN`, a rule that rewrote an early `abstain` to `again`.
Nothing in the RFC, the decisions, or build spec 4.2 asks for that, and it made
abstain require three consecutive refusals while the pile of plausible-looking
near misses in front of the model grew with every pass. Removed 2026-09-07 in
session 4g.
"""

from __future__ import annotations

import logging

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END

from app import settings
from app.state import Doc, Reflection, RetrievalState

log = logging.getLogger(__name__)

MAX_ITERATIONS = 3
# There is deliberately no minimum-passes rule on `abstain`. The argument for
# one was that abstain is the most expensive decision in the graph, so it should
# be earned by three refusals. Live on `abs_002` that argument inverted: the
# model said abstain on pass 1 and pass 2, was overruled both times, and on pass
# 3, now looking at eight near-miss documents instead of three, said done. The
# rule did not make abstain more considered, it made it harder to reach the
# longer the model looked. The cap that matters is still the edge below.
TEXT_PREVIEW = 600

SYSTEM = """You decide whether a documentation search found enough to answer a \
support ticket.

The knowledge base is **API reference documentation only**: one page per route \
per version, plus one error code table per product area. It has no runbooks, no \
best-practice guides, no capacity or pacing advice, no tuning recommendations. \
Judge coverage against what reference documentation can contain, not against \
everything the customer would like to hear.

You see the ticket and every document retrieved so far, across every search \
pass. Choose exactly one decision.

- "done": the retrieved documents contain the reference facts the answer will \
be built from. Put in `keep` the doc_ids the drafter actually needs and nothing \
else. Two or three is typical, one is fine, five is too many. Leave out near \
misses, wrong-version documents, and anything the answer would not cite. Being \
selective is the point of this step: only what you keep is passed forward.
- "again": a specific document you can name almost certainly exists and has not \
come back yet. Put in `missing` one sentence naming that route, error code, or \
fact, phrased so a query planner can search for it. Leave `keep` empty.
- "abstain": nothing retrieved answers the question this ticket asks, and the \
kind of fact it asks for is not something reference documentation carries. \
Reference documentation for these routes does not discuss service levels, \
pricing, client libraries for any language, where data is stored \
geographically, or sending many operations in one request. Leave `keep` empty. \
Abstaining is a correct answer, not a failure: a human reviewer gets a gap \
report and the customer does not get an invented one.

Rules:

- Only ever put doc_ids in `keep` that appear in the list you were shown.
- **Partial coverage is "done", not "again".** If the retrieved routes answer \
the mechanical part of the question and the rest is operational advice the \
reference docs never carry, choose done. The drafter is instructed to say \
plainly which parts the docs do not cover.
- **The same subject area is not coverage.** A document covers this ticket only \
if it answers the specific question asked. A page about the route the ticket \
names, or about the neighbouring operation, that never addresses what was \
actually asked, is a near miss. Documentation showing how one operation works \
is not evidence about whether some different operation exists. If near misses \
are all that came back, that is "abstain", not "done" with them in `keep`.
- Choose "again" only when you can name the missing document. "There might be \
more" is not a reason. If an earlier pass already asked for something and it \
did not come back, it does not exist: decide with what you have.
- Mind the version. A v2 document does not answer a v3 ticket unless the ticket \
asks how the two differ, in which case keep both.
- A document marked deprecated is the right answer to "why did this route stop \
working", together with whatever it was replaced by."""


def _render(results: list[Doc]) -> str:
    lines = []
    for doc in results:
        text = doc["text"][:TEXT_PREVIEW]
        lines.append(
            f"- doc_id: {doc['doc_id']}\n"
            f"  source: {doc['source']}\n"
            f"  route: {doc['route'] or '(error table row)'}\n"
            f"  version: {doc['version']}\n"
            f"  status: {doc['status']}"
            + (f"\n  replaced_by: {doc['replaced_by']}" if doc.get("replaced_by") else "")
            + (f"\n  error_code: {doc['error_code']}" if doc.get("error_code") else "")
            + f"\n  description: {doc['description']}\n"
            f"  text: {text}"
        )
    return "\n".join(lines)


LAST_PASS = (
    "\n\nThis is the last search pass. \"again\" is not available: choose done "
    "with the best doc_ids you have, or abstain if the knowledge base genuinely "
    "does not cover this subject."
)


def _user_prompt(state: RetrievalState, results: list[Doc]) -> str:
    ticket = state["ticket"]
    last = LAST_PASS if state.get("iteration", 1) >= MAX_ITERATIONS else ""
    # A reviewer rerun carries a hint. Reflect has to see it too: otherwise it
    # drops the document the reviewer explicitly asked for as "wrong version".
    hint = state.get("hint")
    hint_note = (
        f"\n\nA human reviewer re-ran this search and asked for: {hint}\n"
        "Keep what they asked for if it came back, whatever version it is in."
        if hint
        else ""
    )
    return (
        "Ticket\n"
        f"  api_version: {ticket['api_version']}\n"
        f"  product_area: {ticket['product_area']}\n"
        f"  subject: {ticket['subject']}\n"
        f"  body: {ticket['body']}\n\n"
        f"Search pass {state.get('iteration', 1)} of {MAX_ITERATIONS}. "
        f"{len(results)} document(s) retrieved so far:\n\n"
        f"{_render(results)}"
        f"{hint_note}"
        f"{last}"
    )


def reflect(state: RetrievalState, config: RunnableConfig) -> dict:
    """Decide done, again, or abstain over everything retrieved so far."""
    # Branches ran concurrently and two indexes can return the same doc, so the
    # model sees each document once.
    results = list({d["doc_id"]: d for d in state.get("results", [])}.values())
    iteration = state.get("iteration", 0)

    if not results:
        log.info("reflect: nothing retrieved on pass %d", iteration)
        if iteration >= MAX_ITERATIONS:
            return {
                "decision": "abstain",
                "keep": [],
                "missing": "three search passes returned no documents at all",
            }
        return {
            "decision": "again",
            "keep": [],
            "missing": "no documents matched. Try a broader description of the symptom",
        }

    try:
        model = settings.chat_model("fast").with_structured_output(Reflection)
        reflection: Reflection = model.invoke(
            [("system", SYSTEM), ("human", _user_prompt(state, results))],
            config,
        )
        decision = reflection.decision
        keep = list(reflection.keep)
        missing = reflection.missing
    except Exception:
        log.exception("reflect model call failed, abstaining")
        return {
            "decision": "abstain",
            "keep": [],
            "missing": "the reflection step errored, so retrieval could not be verified",
        }

    valid = {d["doc_id"] for d in results}
    dropped = [doc_id for doc_id in keep if doc_id not in valid]
    if dropped:
        log.warning("reflect: dropping %d doc id(s) that were never retrieved: %s", len(dropped), dropped)
    keep = [doc_id for doc_id in dict.fromkeys(keep) if doc_id in valid]

    if decision == "done" and not keep:
        # "Done with nothing" is not an answer the drafter can use.
        log.info("reflect: 'done' with an empty keep list, treating as no coverage")
        decision = "abstain"
        missing = missing or "nothing retrieved was relevant to this ticket"

    if decision == "again" and iteration >= MAX_ITERATIONS:
        # RFC 3.3: `again` on the last pass is the abstain exit. The edge stops
        # the loop either way, this makes the disposition honest about why.
        log.info("reflect: 'again' on pass %d, converting to abstain", iteration)
        decision = "abstain"

    if decision != "done":
        keep = []

    log.info(
        "reflect pass %d: %s, keeping %d of %d%s",
        iteration,
        decision,
        len(keep),
        len(results),
        f", missing: {missing}" if missing else "",
    )
    return {"decision": decision, "keep": keep, "missing": missing}


def route_after_reflect(state: RetrievalState) -> str:
    """`again` under the cap goes back to planning. Everything else ends the subgraph."""
    if state.get("decision") == "again" and state.get("iteration", 0) < MAX_ITERATIONS:
        return "plan_queries"
    return END
