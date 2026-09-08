# Eval results

Rewritten 2026-09-07 against the final experiments of session 4f. Every number
below is measured, not estimated. Where a number is weak evidence, this file
says so rather than rounding it up into a claim.

The two experiments this file reports are `e2e-hybrid-final-3e605725` and
`retrieval-hybrid-tuned-reflect-3aa1e54a`. The end to end run is a rerun on
2026-09-07 of `e2e-hybrid-final-f3a79b86` with identical prompts, made because the
first run only got 57 of 90 traces into LangSmith before a quota limit; the rerun
ingested 90 of 90 and its scores are the ones below. The baseline they are compared
against, and the two prompt changes between them, are in `docs/tuning-log.md`.

| | |
|---|---|
| Datasets | `apidocs-golden` (30 examples), `apidocs-retrieval` (27), both tagged `v2` |
| Generation model | `gpt-5.6-luna` (fast), `gpt-5.6-sol` (strong) |
| Judge model | `gpt-5.6-sol`, hand-rolled binary judge, calibrated 10 of 10 |
| Repetitions | 3 end to end, 1 on the retrieval-only runs |
| Answer cache | Off. Every run uses `use_cache=False` |
| Column names | `escalate_correct` and `abstained`, per build spec 8.3 as of 2026-09-07 |

## 1. Headline

**The abstain path now works, and correctness is still the thing that is not
ready.**

| Split | n | Correctness mean | Correctness pass^3 | escalate_correct mean | escalate_correct pass^3 |
|---|---|---|---|---|---|
| L1 | 9 | 0.85 | 0.78 | 1.00 | 1.00 |
| L2 | 8 | 0.67 | 0.50 | 1.00 | 1.00 |
| L3 | 4 | 0.00 | 0.00 | 1.00 | 1.00 |
| abstain | 6 | — | — | **1.00** | **1.00** |
| escalate | 3 | — | — | 1.00 | 1.00 |
| near_miss | 6 | 0.89 | 0.83 | 1.00 | 1.00 |

Correctness is blank on the abstain and escalate splits by design. Those
examples have no reference answer to match, and scoring them zero would punish
the system for behaving correctly.

`escalate_correct` asks one question, did the system escalate exactly when the
reference says escalate. It is a triage measurement and nothing else. Whether an
abstain ticket then abstained is measured on the retrieval subgraph in section 3,
which is where that decision is actually made.

Four things to read off this table.

**`escalate_correct` is 1.00 on all 90 runs.** All three escalate examples
escalated on all three trials. Nothing else escalated on any trial. Before the
triage prompt change in session 4f, the abstain split scored 0.61 mean and 0.50
pass^3 on this column, because three abstain tickets were being escalated for
being about pricing, service levels, or data residency. See section 4.

**The near-miss split is still the strongest correctness result.** 0.89 mean and
0.83 pass^3 on the six examples specifically built to confuse a retriever
between a route and its lookalike. Retrieval is picking the right one of a
confusable pair, reliably. That is the thing this architecture was built to do
and it is doing it.

**L2 is the weakest answer split now, at 0.67 mean and 0.50 pass^3.** Section 3
shows why. Six of eight L2 examples retrieve exactly two of their three expected
documents, and the one they drop is usually the error-table row.

**L3 is 0.00 and that number is softer than it looks.** Every L3 failure is the
same failure, the draft picks one API version and answers confidently for it
where the reference covers both and asks the developer which they are on. The
judge comments in section 5 say this in almost identical words on all four.
Section 6 explains why the dataset fix made this harder to read, not easier.

## 2. Trajectory columns

Four deterministic checks, read off the target's output dict rather than the run
tree.

| Check | Scored on | Result |
|---|---|---|
| `traj_searched` | 21 answer examples, 63 runs | 1.00 mean, 1.00 pass^3 |
| `traj_iterations_ok` | 27 examples, 81 runs | 1.00 mean, 1.00 pass^3 |
| `traj_abstain_exit` | 6 abstain examples, 18 runs | **0.89 mean, 0.83 pass^3** |
| `traj_no_send_before_review` | all 30 examples, 90 runs | 1.00 mean, 1.00 pass^3 |

`traj_no_send_before_review` passing on all 90 runs is the one that matters most
and the one that would be least visible without the check. Nothing reached
`send` without a human decision in state, ever, including on the runs where the
system got the answer wrong. The interrupt holds.

`traj_iterations_ok` is scored on 27 of the 30 examples and 81 of the 90 runs.
The three excluded examples are the escalate ones, which skip retrieval by
design. In the session 4f baseline this column was scored on 26 examples and 74
runs, and the missing seven runs were abstain tickets that triage escalated
before retrieval could run. That column reaching its ceiling is the cleanest
single piece of evidence that the triage fix landed.

**`traj_abstain_exit` is the honest counterweight to section 1.** It is the
end-to-end shadow of `abstained`, and at 0.89 mean and 0.83 pass^3 it says two
of eighteen abstain runs still ended without the abstain exit firing, and one of
six abstain examples was not reliable across three trials. The retrieval-only
experiment scored the same six examples at 1.00 on one repetition. Both numbers
are real. Read together they say the abstain path fires far more often than it
did and is not yet deterministic, which is exactly what six examples and three
trials can support.

## 3. Retrieval, the diagnostic

`retrieval-hybrid-tuned-reflect-3aa1e54a`, the subgraph alone, 27 examples, one
repetition.

| Split | n | Recall | Precision | abstained |
|---|---|---|---|---|
| L1 | 9 | **1.00** | 0.78 | 1.00 |
| L2 | 8 | 0.67 | 0.83 | 0.88 |
| L3 | 4 | 0.47 | 0.79 | 1.00 |
| abstain | 6 | **1.00** | **1.00** | **1.00** |
| near_miss | 6 | 0.89 | 0.94 | 1.00 |
| **All** | **27** | **0.82** | **0.85** | **0.96** |

This is the table that turns "the answer was wrong" into "and here is which half
to fix".

**L1 recall is a perfect 1.00.** Every single-doc lookup found its doc. So every
L1 correctness failure is a drafting failure, not a retrieval one. That is a
direct read, not an inference.

**The abstain row is 1.00 on all three columns.** All six abstain examples
returned no documents, kept none, and set the `abstained` flag. Recall and
precision are 1.00 by the empty-set convention, which is to say the subgraph
handed the drafter nothing on a question the corpus does not cover, which is the
correct behaviour. In the session 4f baseline this row read 0.83 across the
board, with `abs_006` answering off two same-area endpoint docs.

**L2 recall is 0.67, and the shape is regular.** Five of the eight L2 examples
score exactly 0.667, which is two of three expected docs. The retriever is not
failing to understand these tickets, it is stopping one doc short, and the doc it
drops is usually the error-table row or the cross-area doc. `l2_006` is worse
than that, it scored 0.00 and the subgraph abstained on it, which is the one
false abstain in this run.

**L3 recall is 0.47 and every miss is the other version's doc.** `l3_001` 0.40,
`l3_002` 0.50, `l3_003` 0.667, `l3_004` 0.333. The retriever is fetching one
version's docs and the reference needs both. Section 6 explains why that is
partly the eval's own fault.

**`abstained` at 0.96 overall is the abstain metric, and 0.96 is 26 of 27.** The
one failure is `l2_006`, an answerable ticket the subgraph refused. There are no
false answers left on the abstain split in this run, and one false refusal on the
answer side. The two error types are not symmetric in cost and the remaining one
is the cheaper of the two, since a false refusal produces a gap report to a human
and a false answer produces a confident wrong answer to a bank developer.

## 4. The abstain path, and what fixed it

The 2026-09-06 experiment had all six abstain examples failing a single
`disposition` column. Session 4g split that column in two, because it was
carrying two unrelated verdicts. Session 4f then diagnosed and fixed both halves
in prompt text. Full detail, including the reverted first attempt, is in
`docs/tuning-log.md`.

| Half | Where it is scored now | Baseline | Final |
|---|---|---|---|
| Did triage escalate an abstain ticket | `escalate_correct`, abstain split | 0.61 mean, 0.50 pass^3 | **1.00 / 1.00** |
| Did the subgraph abstain when it should | `abstained`, abstain split | 0.83 | **1.00** |

**Bug 1, triage escalated before retrieval ran.** `abs_001`, `abs_003` and
`abs_005` were escalated on some or all trials, `retrieval_stats` was `None` on
those runs, and the gap report abstain exists to produce was never written. The
cause was a collision between two specs rather than a model ignoring its prompt.
Build spec 5.5 makes pricing, service levels and data residency the topics the
corpus deliberately does not cover. Build spec 4.2 puts billing and legal on the
triage escalate list. A question about what a transaction costs is a billing
question, and questions about availability commitments and data jurisdiction read
as legal, so those tickets genuinely matched the escalate list they were shown.
The fix changes the escalate test from what the ticket is about to who has to act
next. Escalate when the provider has to do something to the account that the
customer cannot do through the API. A ticket that asks how to do something, or
which route to call, is a question however forcefully it states what it wants to
happen.

**Bug 2, reflect answered on same-area documents.** `abs_006` retrieved the
create-one-endpoint and delete-one-endpoint docs for a question about whether a
bulk form of those operations exists, and reflect called that coverage. The fix
adds one rule, a document covers the ticket only if it answers the specific
question asked, and a page about the route the ticket names that never addresses
what was asked is a near miss rather than coverage.

Both fixes are category-level rules. Neither prompt names any example, topic, or
ticket from the dataset. There is no holdout, so both carry the overfitting
caveat in section 8.

## 5. Every failing example, with a one-line diagnosis

Retrieval or drafting, decided by cross-referencing each correctness failure
against that example's row in `retrieval-hybrid-tuned-reflect-3aa1e54a`. If
retrieval brought back every expected doc and the answer is still wrong, the bug
is downstream. That cross-reference is across two experiments rather than within
one, since the retrieval-only run is a separate execution, so it is a strong hint
rather than a proof for any single trial.

The "what went wrong" column quotes the judge's own comment on a failing trial,
not a later reconstruction.

Failing examples on the reported run, `e2e-hybrid-final-3e605725`, by trial: `l1_001` [0,1,1],
`l1_004` [0,0,0], `l2_001` [0,1,1], `l2_002` [1,0,0], `l2_006` [0,0,0],
`l2_007` [1,0,0], and all four L3 examples [0,0,0]. The per-example table below
was written against the first final run with the same prompts, so two L2 rows
differ (`l2_003` and `l2_008` passed on the rerun, `l2_001` failed on it). The
pattern is the same on both runs: every L3 example fails every trial, and L2
failures sit on examples whose retrieval came back one document short.

### Correctness failures

| Example | Trials | Diagnosis | What went wrong |
|---|---|---|---|
| `l1_001` | 2/3 | **drafting** | Retrieval recall 1.00. One trial of three failed and its trace was not ingested, so no judge comment is available for it. |
| `l1_004` | 0/3 | **drafting** | Retrieval recall 1.00 in the final run. Judge: the draft "incorrectly implies the key may need investigation instead of explaining that sandbox is deliberately limited to 30 requests/minute". |
| `l2_002` | 1/3 | **retrieval** | Recall 0.667. Judge: the draft "incorrectly qualifies v3 event replay with 'unless restricted'". |
| `l2_003` | 1/3 | **retrieval** | Recall 0.667. Judge: the draft sends the developer to `POST /v3/webhooks/endpoints/{id}/test`, "which is not a route given in the reference answer". |
| `l2_006` | 0/3 | **retrieval** | Recall 0.00 and the subgraph abstained. Judge: the draft "incorrectly says the information is unavailable and omits the v3 limits (600/min production, 30/min sandbox)". |
| `l2_007` | 1/3 | **drafting** | Recall 1.00. Judge: the draft claims "v3 provides no complete guarantee of duplicate prevention for an identical key and body", contradicting the reference. |
| `l2_008` | 2/3 | **retrieval** | Recall 0.667. Judge: the draft says refunds must wait for settlement, where `PAY_4023` means already captured and refund is the right call. |
| `l3_001` | 0/3 | **retrieval and drafting** | Recall 0.40. Judge: "the draft assumes v2 and recommends only `/v2/payments/{id}/void`" where the version is unknown. |
| `l3_002` | 0/3 | **retrieval and drafting** | Recall 0.50. Judge: the answer "must cover both v2 offset pagination and v3 cursor pagination and ask which is in use; the draft incorrectly assumes v3 only". |
| `l3_003` | 0/3 | **retrieval and drafting** | Recall 0.667. Judge: "the draft answers only for v2 and omits the v3 limit of 90 days". |
| `l3_004` | 0/3 | **retrieval and drafting** | Recall 0.333. Judge: "the draft assumes v3 and omits the v2 behavior … the shared account-level signing secret". |

Three drafting failures, four retrieval failures, four that are both. All four
L3 examples fail the same way and the judge says so in near-identical language on
each, which is a stronger signal than four unrelated failures would be.

The `WHK_4290` fabrication claim that appeared in this table before 2026-09-07 is
gone. It was checked against the corpus and it was wrong. `WHK_4290` is a real
row in `kb/errors/webhooks.md`, named in both `deliveries-retry` docs, and the
draft cited a real code that was wrong for the question.

### escalate_correct failures

None. All 30 examples passed on all three trials.

## 6. What the dataset fix cost, stated plainly

Three L3 tickets (`l3_002`, `l3_003`, `l3_004`) shipped with
`api_version: "unknown"`, which the frozen `Ticket` type forbids and `intake`
rejects, so they errored at the first node on every repetition. The fix chosen
was to set a concrete version on those three rows and bump the dataset to `v2`.

That fix has a cost and the L3 numbers should be read with it in hand.
`api_version` is what the retrieval planner falls back to when a query does not
name a version. Setting it hands those examples a version hint their ticket body
deliberately withholds, while their reference answers still require covering both
versions and asking which one. The retrieval table shows exactly this, every L3
miss is the other version's doc.

So **L3 at 0.00 correctness is not purely a system failure.** Part of it is the
eval telling the system "this tenant is on v3" and then failing it for answering
for v3. `l3_001` is the control. It always carried a concrete `v2`, was untouched
by the fix, and fails the same way. That suggests the system would score poorly
on L3 regardless, but 0.00 across four examples overstates it.

The honest version for the deck is that the system does not currently handle
version-ambiguous tickets, and the L3 eval as it stands cannot measure how badly.
Widening `Ticket.api_version` to include `unknown` is the fix on both sides.

## 7. Reliability, cost, and latency

Read back from LangSmith over the root runs of `e2e-hybrid-final-3e605725`.

| | |
|---|---|
| Root runs ingested | 90 of 90 |
| Median latency | 17.5 s |
| p90 latency | 34.6 s |
| Max latency | 55.5 s |
| Mean cost per ticket | $0.0121 |
| Mean tokens per ticket | 6,453 |
| Total cost, 90 runs | $1.09 |

These numbers cover all 90 runs. The first final run, `e2e-hybrid-final-f3a79b86`, hit the
LangSmith monthly unique-traces limit partway through and only 57 of its 90
traces were ingested. The quota was lifted and the experiment rerun with the same
prompts; the rerun is the one reported everywhere in this file. The baseline run
of the same graph measured a median of 16.7 s, p90 35.5 s, max 54.8 s, and
$0.0124 mean cost per ticket, so nothing here moved.

Against a stated baseline of two hours to a day per ticket, 18 seconds and one
cent is not the constraint. Nothing in these results argues against continuing on
cost or latency grounds. The argument is entirely about correctness on L2 and L3.

**On pass^3 versus pass@3.** Every reliability number in this file is pass^k,
meaning the example passed on all three trials. pass@k, which asks whether any
one of three trials passed, would make this system look considerably better and
would describe a situation nobody actually operates in. L1 correctness is 0.85
mean and 0.78 pass^3; the gap between those two numbers is the system's
run-to-run non-determinism, and it is the honest thing to show rather than hide.

## 8. What this sample size can and cannot support

Per the eval research notes.

**Legitimate to claim from these results.**

- Directional strength and weakness by split. Near-miss is strong, L3 is broken,
  and those are different enough to act on separately.
- That the abstain mechanism now fires, checked deterministically at the
  trajectory level and on the subgraph rather than by a judge's opinion.
- That triage escalates exactly the three tickets it should, 90 runs of 90.
- That nothing reaches send without a human decision. 90 of 90, deterministic.
- Relative comparison between two experiment runs on the same frozen dataset,
  which is what the session 4f before-and-after is and what the semantic-only
  ablation in section 9 is.
- That every L1 correctness failure is downstream of retrieval, since L1
  retrieval recall is exactly 1.00.

**Not legitimate to claim.**

- Any of these percentages as a forecast of accuracy on real bank developer
  traffic. This is a 30-example synthetic golden set whose corpus and questions
  were written by the same person.
- That the abstain mechanism is reliable. Six examples bound confidence very
  loosely, and `traj_abstain_exit` at 0.83 pass^3 says one of those six is still
  not reliable across three trials.
- That the two prompt changes generalise. There is no holdout. Both were tuned
  against these 30 examples and scored on the same 30. They were written as
  category-level rules with no example-specific wording precisely to limit that
  risk, and that is a mitigation, not a measurement.
- That the reference answers are correct. They were written by an agent and were
  never verified by a human.
- That the judge's pass or fail is ground truth. It is a proxy calibrated against
  ten hand-labelled pairs, at 10 of 10 agreement with TPR 1.00 and TNR 1.00, and
  it should be presented that way. The calibration set is balanced 5 and 5
  precisely so agreement is not flattered by a rare failure class.

The framing that holds up under pushback is that this is a 30-example set,
deliberately small for a short build. It is enough to catch whether the abstain
mechanism works at all, which it now does, and enough to catch gross regressions
between runs. It is not enough for a production confidence interval. The next
investment is the trace-mining loop, where every reviewed ticket grows this
dataset for free.

## 9. Hybrid versus semantic only

The ablation. `semantic_only` rewrites every planned exact lookup into a semantic
one, so the `(route, version)` and `error_code` indexes are effectively removed
and the system finds documents purely by embedding similarity. Same dataset, same
tag, same models, same three repetitions. The only variable is the retrieval mode.

**These are the session 4e numbers and they were not rerun.** Both sides of the
ablation predate the 2026-09-07 reflect change and both prompt changes in session
4f, so its "hybrid" column is not the same hybrid as the rest of this file. It is
kept because its claim is about retrieval recall, and neither the reflect change
nor the triage change touches how documents are found.

The near-miss split is the one built to detect this, six examples that name or
imply one route of a confusable pair, where an embedding search has every reason
to return the lookalike.

### Near-miss, the split the ablation targets

| Metric | hybrid (4e) | semantic only (4e) | Change |
|---|---|---|---|
| Correctness mean | 0.94 | 0.83 | **-0.11** |
| Correctness pass^3 | 0.83 | 0.67 | **-0.16** |
| Retrieval recall | 0.89 | 0.83 | -0.06 |
| Retrieval precision | 0.83 | 0.75 | -0.08 |

The near-miss split regressed on all four measures. pass^3 is the sharpest of
them, one more of the six examples stopped being reliable across three trials.

### Every split, both modes

| Split | Correctness hybrid | Correctness semantic | Recall hybrid | Recall semantic |
|---|---|---|---|---|
| L1 | 0.67 | 0.85 | **1.00** | **0.83** |
| L2 | 0.71 | 0.62 | 0.71 | 0.62 |
| L3 | 0.00 | 0.00 | 0.47 | 0.39 |
| abstain | — | — | 0.33 | 0.50 |
| near_miss | 0.94 | 0.83 | 0.89 | 0.83 |
| **All** | | | **0.69** | **0.63** |

### Reading this honestly

**The clean result is retrieval recall.** Overall recall drops 0.69 to 0.63, and
L1 drops from a perfect 1.00 to 0.83. L1 is single-doc exact lookup, which is
precisely what the exact index exists for, so a drop there is the ablation doing
what an ablation should, removing a component and watching the thing that
component was responsible for get worse. L2, L3 and near-miss recall all drop
too. Five of five splits regress on recall.

**The near-miss correctness regression is real but modest**, and at six examples
across three trials, a 0.94 to 0.83 move is two failing runs turning into three.
It points the right way and it is consistent with the recall drop underneath it,
but it is not by itself a strong number.

**L1 correctness went up, from 0.67 to 0.85, while L1 recall went down.** That is
the uncomfortable cell in the table and it should not be quietly dropped. Nine
examples, three trials, and the L1 correctness failures in that hybrid run were
all diagnosed as drafting failures rather than retrieval ones, so this is most
likely run-to-run variance in the drafting step rather than the ablation
improving anything. But it cannot be proven from this data, and at this sample
size a swing of that size in either direction is not surprising. Anyone
presenting the ablation should show this cell rather than crop it.

**The defensible claim.** Removing the exact index measurably degrades retrieval
across every split, with the sharpest single drop on the L1 single-doc lookups
the index is built for, and the near-miss split degrades on all four of its
measures. That is a real, directional, same-dataset regression claim, which is
exactly the class of claim the eval research notes say a frozen
dataset supports. What it does not support is a precise "hybrid is 11 points
better" headline.

## 10. Experiments

Every run below went against the dataset tag, never against "whatever is in the
dataset today". The six session 4f runs carry `prompt_version` in their
metadata, which is what the `--label` flag writes.

| Experiment | Dataset | Runs | Prompts | LangSmith |
|---|---|---|---|---|
| `e2e-hybrid-baseline-f8d72021` | `apidocs-golden@v2` | 90 | before 4f | [compare](https://smith.langchain.com/o/21a29963-af98-5735-9e74-caf17e65ce74/datasets/4b6a9182-3270-4d24-b447-9c22e335ec7d/compare?selectedSessions=afaa9543-7aaf-4aed-aa6e-f531c9ba12c8) |
| `retrieval-hybrid-baseline-e81b6741` | `apidocs-retrieval@v2` | 27 | before 4f | [compare](https://smith.langchain.com/o/21a29963-af98-5735-9e74-caf17e65ce74/datasets/6c685a29-0a32-43c9-8a17-1404a005651b/compare?selectedSessions=e3268e2f-4cc6-4ea2-8d94-d3da25e70419) |
| `e2e-hybrid-tuned-triage-0eb2e9c1` | `apidocs-golden@v2` | 90 | triage attempt 1, reverted | [compare](https://smith.langchain.com/o/21a29963-af98-5735-9e74-caf17e65ce74/datasets/4b6a9182-3270-4d24-b447-9c22e335ec7d/compare?selectedSessions=5df75caf-0650-45b2-a186-d21a7851bcef) |
| `retrieval-hybrid-tuned-reflect-3aa1e54a` | `apidocs-retrieval@v2` | 27 | **final** | [compare](https://smith.langchain.com/o/21a29963-af98-5735-9e74-caf17e65ce74/datasets/6c685a29-0a32-43c9-8a17-1404a005651b/compare?selectedSessions=268890b0-b791-4021-9ef0-3e2effa5407d) |
| `e2e-hybrid-final-3e605725` | `apidocs-golden@v2` | 90 | **final**, rerun with 90 of 90 traces ingested | [compare](https://smith.langchain.com/o/21a29963-af98-5735-9e74-caf17e65ce74/datasets/4b6a9182-3270-4d24-b447-9c22e335ec7d/compare?selectedSessions=454f4ba3-4500-41e6-bfcc-b2a97d1404ad) |
| `e2e-hybrid-final-f3a79b86` | `apidocs-golden@v2` | 90 | same prompts as final, superseded, 57 of 90 traces ingested | [compare](https://smith.langchain.com/o/21a29963-af98-5735-9e74-caf17e65ce74/datasets/4b6a9182-3270-4d24-b447-9c22e335ec7d/compare?selectedSessions=ba30a31b-e096-49ab-bd18-87e3c91b9403) |
| `e2e-semantic-only-e332b83e` | `apidocs-golden@v2` | 90 | 4e, reused for section 9 | [compare](https://smith.langchain.com/o/21a29963-af98-5735-9e74-caf17e65ce74/datasets/4b6a9182-3270-4d24-b447-9c22e335ec7d/compare?selectedSessions=5154a4e0-86f3-46a0-bfc5-b451af9d0564) |
| `retrieval-semantic-only-9a3159e1` | `apidocs-retrieval@v2` | 27 | 4e, reused for section 9 | [compare](https://smith.langchain.com/o/21a29963-af98-5735-9e74-caf17e65ce74/datasets/6c685a29-0a32-43c9-8a17-1404a005651b/compare?selectedSessions=8b06a8f2-63df-4824-adc6-e44ab5c255c1) |

The retrieval experiment was not rerun after the second triage rewrite.
`run_retrieval_only` calls the subgraph directly and never invokes triage, so a
triage prompt cannot change its result.

Every experiment carries `retrieval_mode`, `git_sha`, `dataset_version`,
`model_fast`, `model_strong`, `judge_model` and `use_cache` in its metadata, and
the session 4f runs add `prompt_version`. LangSmith does not prescribe an
experiment metadata schema, so that list is a project convention set deliberately
rather than one the platform enforces.

## 11. Automate today, or keep a human

The table this whole file is built for.

| Ticket type | Evidence | Recommendation |
|---|---|---|
| Near-miss L1/L2 | correctness 0.89, pass^3 0.83, recall 0.89, precision 0.94 | **Draft and review.** The strongest split, and still not unattended. |
| L1 single-doc | recall 1.00, correctness 0.85, pass^3 0.78 | **Draft and review.** Retrieval is solved here, drafting is not. |
| L2 synthesis | correctness 0.67, pass^3 0.50, recall 0.67, consistently one doc short | **Draft and review, and fix retrieval first.** The weakest answerable split. |
| L3 version-ambiguous | correctness 0.00 across four examples, every trial | **Escalate with no draft.** The system answers one version confidently and does not ask. |
| Not a docs question | `escalate_correct` 1.00, pass^3 1.00, all three examples | **Escalate, no draft.** Working as designed. |
| Uncovered by the docs | `abstained` 1.00 on the subgraph, `traj_abstain_exit` 0.89 end to end | **Gap report and review.** The path works and is not yet deterministic, so a human still reads the gap report. |

The last row is the one that changed. In the previous run it read "do not ship".
It now says ship it behind a human, on the strength of two measurements taken
where the decision is made, not one column carrying two verdicts.

Nothing here is ready to send unattended. That is not a disappointing result at
this stage, it is the result the human-in-the-loop architecture was designed
around, and `traj_no_send_before_review` at 90 of 90 is the evidence the design
holds even when the answers do not.

## 12. What to fix first

1. **The query planner, for the missing error-table row.** Five of eight L2
   examples stop exactly one doc short, and the doc is usually the error-table
   row. `l1_004` and `l2_006` are the same failure at its worst, three semantic
   passes for a document the exact `error_code` index would have returned first
   time. This is now the largest single source of wrong answers.
2. **Widen `Ticket.api_version` to include `unknown`.** Fixes the L3 eval and the
   L3 behaviour at once, and lets section 6's caveat be deleted.
3. **The draft prompt, on version ambiguity.** All four L3 failures are one
   behaviour, the draft commits to a version instead of covering both and asking.
   The judge says so in near-identical words on all four.
4. **Hold the abstain path with a regression check.** `traj_abstain_exit` is
   0.83 pass^3. The path works now and both prompts that carry it were tuned
   without a holdout, so it needs to be measured on every future run rather than
   assumed.
