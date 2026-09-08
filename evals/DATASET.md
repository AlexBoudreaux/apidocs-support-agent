# Golden set, v1

30 examples in `evals/dataset.jsonl`, written by session 4b against the frozen corpus in `kb/`. Alex edits every reference answer against the source doc before `upload.py` tags v1.

Read this file to review. One line per example, with the doc it came from and the single fact it tests.

## Counts

| Split | Count | Disposition |
|---|---|---|
| L1 | 9 | answer |
| L2 | 8 | answer |
| L3 | 4 | answer |
| abstain | 6 | abstain |
| escalate | 3 | escalate |
| **near_miss** (second split on L1 and L2) | **6** | 3 on L1, 3 on L2 |

12 of the 30 are the `fixtures/tickets/` tickets reused verbatim, so a dataset id is also a live-demo `thread_id`. They are marked † below.

## Examples

| id | splits | expected_doc_ids | The fact it tests |
|---|---|---|---|
| `l1_001` † | L1 | `payments-refund-v3`, `payments-errors#PAY_4013` | v3 refund window is 90 days after capture, past it PAY_4013 |
| `l1_002` † | L1 | `payments-void-v3` | void is removed in v3, replaced by reversal |
| `l1_003` † | L1, near_miss | `webhooks-deliveries-retry-v3` | retry re-sends one delivery to one endpoint, replay would hit all endpoints |
| `l1_004` † | L1 | `payments-errors#RATE_LIMITED` | sandbox is 30/min in both versions, v3 production is 600/min |
| `l1_005` | L1 | `payments-receipt-v3` | v3 receipt route removed, replaced by GET /v3/payments/{id}?expand=receipt |
| `l1_006` | L1 | `webhooks-ping-v3` | v3 ping removed, replaced by per-endpoint test called once per endpoint |
| `l1_007` | L1, near_miss | `payments-confirm-v3`, `payments-errors#PAY_4030` | capture on an unauthenticated v3 payment returns PAY_4030, confirm first |
| `l1_008` | L1, near_miss | `payments-refund-v3`, `payments-errors#PAY_4023` | reversal only releases an uncaptured authorization, captured means refund (PAY_4023) |
| `l1_009` | L1 | `payments-list-v3` | v3 list is cursor paginated with next_cursor and has_more and no total_count |
| `l2_001` † | L2 | `payments-refund-v3`, `webhooks-events-list-v3`, `payments-errors#PAY_4022` | payment.refunded is the event, and refunding before payment.captured settles gives PAY_4022 |
| `l2_002` † | L2, near_miss | `webhooks-deliveries-retry-v3`, `webhooks-events-replay-v3`, `webhooks-errors#WHK_4100` | retry each failed delivery with v3 backoff, not replay, WHK_4100 after 5 attempts |
| `l2_003` † | L2 | `webhooks-endpoints-create-v3`, `webhooks-deliveries-list-v3`, `webhooks-errors#WHK_4220` | v3 signs per endpoint with the create-time secret, v2 signed with the account secret (WHK_4220) |
| `l2_004` | L2, near_miss | `webhooks-events-list-v3`, `webhooks-deliveries-list-v3`, `webhooks-errors#WHK_4100` | events are one row per event, deliveries are one row per HTTP attempt |
| `l2_005` | L2, near_miss | `payments-confirm-v3`, `payments-capture-v3`, `payments-errors#PAY_4030` | confirm is 3DS and emits payment.confirmed, capture moves money and emits payment.captured |
| `l2_006` | L2 | `webhooks-errors#RATE_LIMITED`, `webhooks-deliveries-retry-v3`, `webhooks-deliveries-list-v3` | v3 rate limits 600/min prod and 30/min sandbox, pace the drain with retry backoff |
| `l2_007` | L2 | `payments-create-v2`, `payments-create-v3`, `payments-errors#PAY_4090` | v2 Idempotency-Key optional and reuse ignored, v3 required with PAY_4090 on body mismatch |
| `l2_008` | L2 | `payments-reversal-v3`, `webhooks-events-list-v3`, `payments-errors#PAY_4023` | reversal releases an uncaptured authorization and emits payment.reversed, PAY_4023 if captured |
| `l3_001` † | L3 | `payments-void-v2`, `payments-reversal-v3`, `payments-refund-v2`, `payments-refund-v3`, `payments-errors#PAY_4023` | uncaptured means v2 void or v3 reversal, captured means refund, then ask version and state |
| `l3_002` | L3 | `payments-list-v2`, `payments-list-v3` | v2 offset with total_count vs v3 cursor with next_cursor and has_more, then ask version |
| `l3_003` | L3 | `payments-refund-v2`, `payments-refund-v3`, `payments-errors#PAY_4013` | refund window is 30 days on v2 and 90 days on v3, then ask version |
| `l3_004` | L3 | `webhooks-endpoints-create-v2`, `webhooks-endpoints-create-v3`, `webhooks-errors#WHK_4220` | v2 account-level secret vs v3 per-endpoint secret returned once, then ask version |
| `abs_001` † | abstain | *(empty)* | corpus says nothing about where data is stored or jurisdiction |
| `abs_002` † | abstain | *(empty)* | corpus says nothing about client libraries or delivery timing commitments |
| `abs_003` | abstain | *(empty)* | corpus says nothing about what a transaction costs or volume tiers |
| `abs_004` | abstain | *(empty)* | corpus says nothing about submitting many payment operations in one request |
| `abs_005` | abstain | *(empty)* | corpus says nothing about availability commitments or maintenance windows |
| `abs_006` | abstain | *(empty)* | corpus says nothing about registering or deleting many endpoints in one request |
| `esc_001` † | escalate | *(empty)* | legal threat over a disputed transaction, not a docs question |
| `esc_002` † | escalate | *(empty)* | exposed production credential needing revocation, not a docs question |
| `esc_003` | escalate | *(empty)* | billing dispute over an invoice, not a docs question |

## Rules this file was checked against

- Counts match the planned split exactly. `near_miss` is 6, split 3 on L1 and 3 on L2.
- Every `expected_doc_ids` entry was grepped against the loaded corpus (`kb/docs/`, `kb/errors/`, `kb/approved/`), not eyeballed. Error codes cite the row id, `<area>-errors#<CODE>`.
- No example cites `approved-seed-001`. Experiments run `use_cache=False`, so the seed is filtered out of both indexes and citing it would fail for the wrong reason.
- Abstain examples have `expected_doc_ids: []` and a non-null reference answer that refuses. Escalate examples have `reference_answer: null` and an empty list.
- The 12 fixture-derived examples were diffed field by field against the fixture JSON on `subject`, `body`, `api_version`, `product_area`, `tenant` and `created_at`. All identical.
- No ticket body contains its answer's route path, except `l1_002`, `l1_005` and `l1_006`, where the developer naming the dead route they are calling is the whole point.
- The abstain topics were re-grepped: zero hits across the loaded corpus for SLA, service level, pricing, price, cost, fee, tier, invoice, SDK, client library, residency, batch, bulk, GDPR, uptime, availability, maintenance window.
- Every L3 reference answer covers both v2 and v3 and ends with a clarifying question, and cites a v2 doc and a v3 doc.

## Calibration pairs

`evals/calibration_pairs.jsonl`, 10 lines of `{id, ticket, reference_answer, draft, label, failure_mode}`. 5 pass, 5 fail.

| id | label | failure mode |
|---|---|---|
| `cal_01` | pass | — |
| `cal_02` | pass | — |
| `cal_03` | pass | — |
| `cal_04` | pass | — |
| `cal_05` | pass | — |
| `cal_06` | fail | right_route_wrong_version |
| `cal_07` | fail | right_route_wrong_version |
| `cal_08` | fail | right_facts_wrong_route |
| `cal_09` | fail | fabricated_fact |
| `cal_10` | fail | confused_near_miss_pair_C |

Two fails are right route wrong version (`cal_06` quotes the v2 30 day window at a v3 ticket, `cal_07` quotes v2 offset pagination at a v3 ticket). One is right facts wrong route (`cal_08` gets the 90 day window right and sends the developer to reversal on a captured payment). The other two are a fabricated field (`cal_09` invents `backoff` on v2 retry) and a collapsed near-miss pair (`cal_10` calls delivery attempts duplicate events).

## Version history

| Tag | What changed | Why |
|---|---|---|
| `v1` | First upload of the file as 4b wrote it. | Gate passed, Alex confirmed every reference answer was edited against the source. |
| `v2` | `api_version` on `l3_002`, `l3_003`, `l3_004` changed from `unknown` to `v3`, `v2`, `v3`. Nothing else. | Those three errored at `intake` and never reached retrieval. `Ticket.api_version` is frozen as `Literal["v2", "v3"]` in build spec section 3 and `app/nodes/intake.py` rejects anything else, so all three failed at the first node on every repetition. Alex chose to set a concrete version on the three rows rather than widen the frozen type. |

Both tags still resolve. `v1` is kept so the shape of the failure stays inspectable; every experiment in `docs/eval-results.md` runs against `v2`.

### What the v2 fix costs, stated plainly

`api_version` is tenant metadata, and the retrieval planner falls back to it when
a query does not name a version. Setting it to a concrete value hands those three
examples a version hint their ticket body deliberately withholds, while their
reference answers still require covering both versions and asking which one. So
L3 now measures something slightly easier than it was written to measure, and an
L3 pass is weaker evidence than an L1 or L2 pass.

`l3_001` already carried a concrete `v2` with a both-versions reference answer,
so this makes the four L3 examples consistent rather than introducing a new
pattern. The version picked per ticket, from the body:

- `l3_002` → `v3`. "Moved it onto the new gateway build", and an undefined
  `total_count` is the v3 cursor-pagination symptom.
- `l3_003` → `v2`. No signal in the body. A three month backlog only bites
  against the v2 30 day window, so v2 is the version that makes the ticket hurt.
- `l3_004` → `v3`. Building the receiver from scratch today, and the colleague
  who saw a per-endpoint secret saw a v3 response.

The alternative, widening `Ticket.api_version` to include `unknown`, is the
domain-correct model and is recorded here as the thing to do if L3 is ever
expanded.
