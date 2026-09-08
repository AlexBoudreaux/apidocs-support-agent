# Tuning log, session 4f, 2026-09-07

Two prompts were changed in this session, `app/nodes/triage.py` and
`app/retrieval/reflect.py`. Nothing else moved. Every number below was measured
in a LangSmith experiment or in a local script whose output is quoted. Nothing
is estimated.

Six experiments ran. Baseline pair, tuned pair, one rerun of the end to end
experiment after the triage prompt was rewritten a second time, and one more
rerun of that with identical prompts after a LangSmith trace quota cut the first
final run's ingestion to 57 of 90 traces. The last one is the reported final.

| Run | Experiment | Prompts as of |
|---|---|---|
| Baseline e2e | [`e2e-hybrid-baseline-f8d72021`](https://smith.langchain.com/o/21a29963-af98-5735-9e74-caf17e65ce74/datasets/4b6a9182-3270-4d24-b447-9c22e335ec7d/compare?selectedSessions=afaa9543-7aaf-4aed-aa6e-f531c9ba12c8) | before this session |
| Baseline retrieval | [`retrieval-hybrid-baseline-e81b6741`](https://smith.langchain.com/o/21a29963-af98-5735-9e74-caf17e65ce74/datasets/6c685a29-0a32-43c9-8a17-1404a005651b/compare?selectedSessions=e3268e2f-4cc6-4ea2-8d94-d3da25e70419) | before this session |
| Triage attempt 1 | [`e2e-hybrid-tuned-triage-0eb2e9c1`](https://smith.langchain.com/o/21a29963-af98-5735-9e74-caf17e65ce74/datasets/4b6a9182-3270-4d24-b447-9c22e335ec7d/compare?selectedSessions=5df75caf-0650-45b2-a186-d21a7851bcef) | triage v1, reflect final. Reverted |
| Final retrieval | [`retrieval-hybrid-tuned-reflect-3aa1e54a`](https://smith.langchain.com/o/21a29963-af98-5735-9e74-caf17e65ce74/datasets/6c685a29-0a32-43c9-8a17-1404a005651b/compare?selectedSessions=268890b0-b791-4021-9ef0-3e2effa5407d) | reflect final |
| Final e2e, first run, superseded | [`e2e-hybrid-final-f3a79b86`](https://smith.langchain.com/o/21a29963-af98-5735-9e74-caf17e65ce74/datasets/4b6a9182-3270-4d24-b447-9c22e335ec7d/compare?selectedSessions=ba30a31b-e096-49ab-bd18-87e3c91b9403) | both final, 57 of 90 traces ingested |
| Final e2e, reported | [`e2e-hybrid-final-3e605725`](https://smith.langchain.com/o/21a29963-af98-5735-9e74-caf17e65ce74/datasets/4b6a9182-3270-4d24-b447-9c22e335ec7d/compare?selectedSessions=454f4ba3-4500-41e6-bfcc-b2a97d1404ad) | both final, 90 of 90 traces ingested |

The retrieval experiment was not rerun after the triage rewrite. It calls
`run_retrieval` directly and never touches triage, so its result is unchanged by
a triage prompt, and rerunning it would have produced the same measurement at
extra cost.

## Caveats

Read these before reading any number in this file.

**The reference answers were written by an agent and were never verified by a
human.** Every correctness number in this file is agreement between two models,
one drafting and one judging, against text a third model wrote. That is a useful
relative signal between two runs of the same system on the same frozen data. It
is not ground truth about whether a bank developer would have been helped.

**There is no holdout.** All 30 examples were used to diagnose the misses and all
30 were used to score the fix. Anything tuned this way is at risk of
overfitting. The rule adopted here is that a prompt change is allowed only when
it is a category level rule change, never wording aimed at a specific example.
Each change below carries a one sentence statement of why it is a rule. No
example id, ticket subject, or topic from the dataset appears in either prompt.

**The sample is small.** The abstain split is six examples. The escalate split is
three. A change that moves the abstain split from five of six to six of six has
moved one example. It is worth having and it is not a reliability claim.

**The retrieval experiment is one repetition.** Its columns are single trial
means, so a flaky example reads as either a clean pass or a clean fail rather
than as flaky. The end to end experiment is three repetitions and reports pass^3.

## Baseline, before any prompt changed

`e2e-hybrid-baseline-f8d72021`, 30 examples, 3 repetitions, 90 runs.

| split | correctness mean | correctness pass^3 | escalate_correct mean | escalate_correct pass^3 |
|---|---|---|---|---|
| L1 | 0.81 | 0.67 | 1.00 | 1.00 |
| L2 | 0.71 | 0.38 | 1.00 | 1.00 |
| L3 | 0.08 | 0.00 | 1.00 | 1.00 |
| abstain | — | — | **0.61** | **0.50** |
| escalate | — | — | 1.00 | 1.00 |
| near_miss | 0.83 | 0.50 | 1.00 | 1.00 |

Trajectory columns, same run.

| Check | n | trials | mean | pass^3 |
|---|---|---|---|---|
| `traj_searched` | 21 | 63 | 1.00 | 1.00 |
| `traj_iterations_ok` | 26 | 74 | 1.00 | 1.00 |
| `traj_abstain_exit` | 6 | 18 | **0.50** | **0.33** |
| `traj_no_send_before_review` | 30 | 90 | 1.00 | 1.00 |

`traj_iterations_ok` is scored on 26 examples and 74 trials rather than the 27
and 81 it should reach, because retrieval never ran on the runs where triage
escalated. The three escalate examples are excluded by design, they are supposed
to skip retrieval. That gap is itself the measurement of miss 1 below.

`retrieval-hybrid-baseline-e81b6741`, 27 examples, 1 repetition.

| split | n | recall | precision | abstained |
|---|---|---|---|---|
| L1 | 9 | 0.89 | 0.63 | 0.89 |
| L2 | 8 | 0.71 | 0.83 | 1.00 |
| L3 | 4 | 0.47 | 0.79 | 1.00 |
| abstain | 6 | 0.83 | 0.83 | **0.83** |
| near_miss | 6 | 0.89 | 0.83 | 1.00 |
| **ALL** | **27** | **0.76** | **0.76** | **0.93** |

Failing examples in the baseline, which is the list every section below
diagnoses.

```
escalate_correct   abs_001 [1, 0, 0]   abs_003 [0, 0, 0]   abs_005 [0, 1, 0]
abstained          abs_006 [0]         l1_004 [0]
```

## Miss 1. `abs_001`, `abs_003`, `abs_005`, triage escalated an abstain ticket

**Label. Spec collision.**

Expected. Triage returns `answer`, retrieval runs, reflect abstains, the drafter
writes a gap report.

What happened. Triage returned `escalate`, the graph went straight to review,
and `retrieval_stats` is `None` on those runs. Measured end to end as
`escalate_correct` [1,0,0] on `abs_001`, [0,0,0] on `abs_003` and [0,1,0] on
`abs_005`. Reproduced before any change with the triage only script, which
escalated `abs_001` and `abs_003` on the run recorded here and passed
`abs_005`, so the behaviour is real and it is not deterministic.

Diagnosis. This is not the model ignoring its prompt. Build spec 5.5 defines the
abstain topics as the things the corpus deliberately does not cover, and three
of them are pricing, service levels, and data residency. Build spec 4.2 defines
the triage escalate list, and it includes billing and legal. A question about
what a transaction costs is a billing question by any reading. A question about
an availability commitment and a question about which jurisdiction holds
cardholder data both read as legal. The two specs overlap, and on that overlap
the ticket genuinely matches the escalate list it was shown. The system was
following its instructions and its instructions collided. The fix therefore has
to change what the escalate rule means, not push harder on the same rule.

## Miss 2. `abs_006`, reflect answered on same area documents

**Label. Model weakness.**

Expected. The subgraph abstains, because the corpus has no batch or bulk route
and says nothing about submitting many operations in one request.

What happened. `abstained` scored 0 in the baseline retrieval experiment.
Reproduced locally, where reflect ended pass 1 with `done, keeping 2 of 6` and
kept `webhooks-endpoints-create-v3` and `webhooks-endpoints-delete-v3`. The
ticket asks whether a hundred and twenty endpoints can be registered and removed
in one request each. The two documents it kept describe creating one endpoint
and deleting one endpoint.

Diagnosis. The retrieved documents are about the right routes and the right
product area, and they do not answer the question, which is whether a bulk form
of those operations exists. Reflect treated topical adjacency as coverage.
The abstain bullet in the prompt already named this category, so the model was
not missing the category, it was applying the wrong test for what counts as a
covering document. That is a fair shot missed, which makes it model weakness and
makes it fixable by stating the test explicitly. The same run showed the
behaviour is flaky, since a later local run of the identical ticket abstained on
pass 1.

## Miss 3. `l1_004`, the subgraph abstained on an answerable ticket

**Label. Model weakness, and not in a prompt this session owns.**

Expected. Retrieval returns `payments-errors#RATE_LIMITED` and the subgraph does
not abstain.

What happened. `abstained` scored 0 in the baseline retrieval experiment, and
recall was 0.00. Reproduced locally. The planner emitted a semantic query on
each of the three passes and never emitted an exact `error_code` lookup, the
semantic index never surfaced the error table row, and reflect said `again` on
passes 1 and 2 naming exactly the document it wanted, then abstained on pass 3.

Diagnosis. Reflect behaved correctly here. It asked twice for the payments error
table row covering HTTP 429, the row exists in the corpus, and it never came
back. Given nothing relevant in front of it on the last pass, abstain is the
right call and the alternative is a fabricated answer. The defect is upstream in
the query planner, which described a symptom semantically three times rather
than looking up an error code exactly, on a ticket whose body contains no code
string to key on. Fixing that means editing the planner prompt, which this
session does not own, so it is diagnosed and left. It is the only false abstain
in the baseline retrieval run.

## Change 1. `app/nodes/triage.py`

**Why this is a rule.** It replaces one category test, escalate when the subject
is legal or billing or account, with a different category test, escalate when
the provider has to act on the account, and the new test is applied to every
ticket in the same way rather than carved out for any of them.

### Attempt 1, reverted

The framing from the session brief, escalate on requests for action and
disputes, not on requests for information.

Local triage script, nine abstain and escalate examples, one trial each. **9 of
9.** All three escalate examples still escalated. On that evidence the run went
out as `e2e-hybrid-tuned-triage-0eb2e9c1`, and the fix broke three answerable
tickets.

| split | baseline escalate_correct | attempt 1 | change |
|---|---|---|---|
| L1 | 1.00 / 1.00 | 0.78 / 0.78 | **-0.22** |
| L2 | 1.00 / 1.00 | 1.00 / 1.00 | — |
| L3 | 1.00 / 1.00 | 0.75 / 0.75 | **-0.25** |
| abstain | 0.61 / 0.50 | **1.00 / 1.00** | +0.39 |
| escalate | 1.00 / 1.00 | 1.00 / 1.00 | — |
| near_miss | 1.00 / 1.00 | 0.83 / 0.83 | -0.17 |

New failures were `l1_003`, `l1_004` and `l3_001`, each [0,0,0], and
`traj_searched` fell to 0.78 on L1 because those tickets never reached
retrieval. All three are answerable documentation tickets that describe an
action the customer wants to take. `l1_003` says "I want you to push that one
message again" and then asks what the correct way to do it is. `l1_004` asks
someone to check whether the sandbox key is broken. `l3_001` needs to cancel a
transaction for a customer who is disputing it with them. The prompt read the
described action as a request for action and escalated. Counted over 90 runs the
change was a wash, seven failures became nine, and it moved them from abstain
tickets, where the cost is a missing gap report, to answerable tickets, where the
cost is a developer who never gets an answer. Reverted.

### Attempt 2, kept

The test became who has to do something next rather than what the ticket is
about. Escalate only when the provider has to act on the customer's account and
the customer cannot do it through the API themselves. A ticket asking how to do
something, or which route to call, is a question however forcefully it states
what the customer wants to happen. A ticket asking why the API responded the way
it did is a question, including when the customer guesses their own account is
at fault. A dispute between the customer and their own customer is not a dispute
with the provider.

Validated before spending an experiment, on all 30 examples rather than the nine
the session script covers, three triage calls each, 90 calls total. **30 of 30
examples passed `escalate_correct` on all three trials.** Then run as
`e2e-hybrid-final-f3a79b86`, and rerun unchanged as `e2e-hybrid-final-3e605725` after the quota
was lifted. Both runs pass `escalate_correct` on all 90 trials.

| split | baseline escalate_correct | final | change |
|---|---|---|---|
| L1 | 1.00 / 1.00 | 1.00 / 1.00 | — |
| L2 | 1.00 / 1.00 | 1.00 / 1.00 | — |
| L3 | 1.00 / 1.00 | 1.00 / 1.00 | — |
| abstain | 0.61 / 0.50 | **1.00 / 1.00** | **+0.39 / +0.50** |
| escalate | 1.00 / 1.00 | 1.00 / 1.00 | — |
| near_miss | 1.00 / 1.00 | 1.00 / 1.00 | — |

All 90 runs passed `escalate_correct`. All three escalate examples still
escalate on all three trials. `traj_searched` is back to 1.00 on every split,
and `traj_iterations_ok` is now scored on 27 examples and 81 trials rather than
26 and 74, which is the direct measurement that every abstain ticket now reaches
retrieval. 27 and 81 is the ceiling, the three escalate examples skip retrieval
by design.

## Change 2. `app/retrieval/reflect.py`

One rule added to the prompt and the abstain bullet reworded. The added rule
says a document covers the ticket only if it answers the specific question
asked, that a page about the route the ticket names which never addresses what
was asked is a near miss, that documentation showing how one operation works is
not evidence about whether a different operation exists, and that near misses
alone mean abstain rather than done. The abstain bullet was changed from "the
knowledge base does not cover the subject of this ticket" to "nothing retrieved
answers the question this ticket asks, and the kind of fact it asks for is not
something reference documentation carries", because the old wording invited
exactly the subject level test that produced miss 2.

**Why this is a rule.** It states the general test for what makes a document
count as coverage, applied to every ticket and every document, and it names no
topic, route, or example from the dataset.

| split | baseline abstained | final | change |
|---|---|---|---|
| L1 | 0.89 | **1.00** | +0.11 |
| L2 | 1.00 | 0.88 | **-0.12** |
| L3 | 1.00 | 1.00 | — |
| abstain | 0.83 | **1.00** | +0.17 |
| near_miss | 1.00 | 1.00 | — |
| **ALL** | **0.93** | **0.96** | **+0.03** |

Recall and precision on the same pair of runs.

| split | recall baseline | recall final | precision baseline | precision final |
|---|---|---|---|---|
| L1 | 0.89 | **1.00** | 0.63 | 0.78 |
| L2 | 0.71 | 0.67 | 0.83 | 0.83 |
| L3 | 0.47 | 0.47 | 0.79 | 0.79 |
| abstain | 0.83 | **1.00** | 0.83 | **1.00** |
| near_miss | 0.89 | 0.89 | 0.83 | 0.94 |
| **ALL** | **0.76** | **0.82** | **0.76** | **0.85** |

**The answer splits have to be read as carefully as the abstain split, and they
say the problem moved rather than only shrank.** All six abstain examples now
abstain, `abs_006` included. But the count of false abstains on answerable
tickets is unchanged at one. It was `l1_004` in the baseline and it is `l2_006`
in the final, and `l1_004` now passes. `l2_006` retrieved nothing the reference
expects, recall 0.00, and abstained on that. As with miss 3 the subgraph refused
on an empty hand rather than answering from near misses, which is the behaviour
the rule asks for, sitting on top of a retrieval miss that the rule does not
address. So on this dataset the reflect change bought all six abstain examples
and cost nothing net on the answer side, and one example is far too little to
call the false abstain rate stable in either direction.

## Not tuned, and why

- **L3 correctness, 0.00 in every run.** The draft picks one API version and
  answers for it where the reference covers both and asks. That is the draft
  prompt, which this session does not own. See `docs/eval-results.md` section 6,
  the dataset fix also hands these tickets a version hint their body withholds.
- **L2 recall stuck at 0.67 on six of eight examples.** The dropped document is
  usually the error table row or the cross area doc. Same root cause as miss 3
  and it lives in the planner prompt, which this session does not own.
- **`l1_004` and `l2_006`, the two false abstains.** Both are query planner
  misses that reflect then handled correctly. Widening reflect to answer on
  weaker evidence would fix the symptom by removing the abstain path, which is
  the opposite of the point.
- **The judge.** Out of scope by instruction, and unchanged between all five
  runs, which is what makes the before and after comparable at all.

## Baseline versus final, every column

End to end, `e2e-hybrid-baseline-f8d72021` against `e2e-hybrid-final-3e605725`.
Both 30 examples, 3 repetitions, 90 runs, same dataset tag, same models, same
judge.

| Column | split | baseline mean | final mean | baseline pass^3 | final pass^3 |
|---|---|---|---|---|---|
| correctness | L1 | 0.81 | 0.85 | 0.67 | 0.78 |
| correctness | L2 | 0.71 | 0.67 | 0.38 | 0.50 |
| correctness | L3 | 0.08 | 0.00 | 0.00 | 0.00 |
| correctness | near_miss | 0.83 | 0.89 | 0.50 | 0.83 |
| escalate_correct | L1 | 1.00 | 1.00 | 1.00 | 1.00 |
| escalate_correct | L2 | 1.00 | 1.00 | 1.00 | 1.00 |
| escalate_correct | L3 | 1.00 | 1.00 | 1.00 | 1.00 |
| escalate_correct | **abstain** | **0.61** | **1.00** | **0.50** | **1.00** |
| escalate_correct | escalate | 1.00 | 1.00 | 1.00 | 1.00 |
| escalate_correct | near_miss | 1.00 | 1.00 | 1.00 | 1.00 |
| traj_searched | all answer splits | 1.00 | 1.00 | 1.00 | 1.00 |
| traj_iterations_ok | all | 1.00 | 1.00 | 1.00 | 1.00 |
| traj_abstain_exit | abstain | **0.50** | **0.89** | **0.33** | **0.83** |
| traj_no_send_before_review | all | 1.00 | 1.00 | 1.00 | 1.00 |

Retrieval, `retrieval-hybrid-baseline-e81b6741` against
`retrieval-hybrid-tuned-reflect-3aa1e54a`. Both 27 examples, 1 repetition.

| Column | split | baseline | final |
|---|---|---|---|
| retrieval_recall | ALL | 0.76 | **0.82** |
| retrieval_recall | abstain | 0.83 | **1.00** |
| retrieval_precision | ALL | 0.76 | **0.85** |
| retrieval_precision | abstain | 0.83 | **1.00** |
| **abstained** | **abstain** | **0.83** | **1.00** |
| abstained | ALL | 0.93 | **0.96** |

Correctness moved on both L1 and near_miss without a prompt on that path
changing, and L2 moved down. Nothing in this session touched the drafter, the
planner, or the judge, so those moves are run to run variance in a system with
three trials per example, not an effect of the tuning. The claim this session
supports is the two bolded rows, `escalate_correct` on the abstain split and
`abstained` on the abstain split, both of which went from a failing number to
every example passing every trial, and both of which are backed by a named
diagnosis and a rule level prompt change.

## Rough edges hit while running this

- The final end to end run hit `Monthly unique traces usage limit exceeded` from
  LangSmith partway through. The experiment completed and every one of the 90
  runs was scored in process, so every score in this file is complete, but only
  57 of the 90 root runs were ingested into the trace project. After the quota
  was lifted the run was repeated unchanged as `e2e-hybrid-final-3e605725`, 90 of 90
  ingested, and that is the run both documents report.
- No OpenAI 429s at `MAX_CONCURRENCY = 8`, in any of the five runs. The
  concurrency raise stands.
- `load_dotenv()` resolves relative to the calling file, so a script piped in on
  stdin gets no API key and LangSmith answers 401. Already hit earlier in
  the build, hit again here, fixed by passing an explicit path.
