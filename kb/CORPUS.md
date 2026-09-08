# Corpus index

Every doc in the knowledge base, with the one fact that makes it distinct. Session 4b authors the golden set against this file and cites these `doc_id`s in `expected_doc_ids`.

Written by session 4a2. Nobody edits `kb/docs/` after this without telling Alex, because reference answers cite these files.

**Counts.** 17 payments route docs, 18 webhooks route docs, 2 error tables, 1 approved answer seed. 38 files. 3 deprecated routes, 4 near-miss pairs, 2 versions.

**Not part of the corpus.** `kb/CORPUS.md` and `kb/FACTSHEET.md` live at the `kb/` root and are documentation about the corpus, not documents in it. The loader reads `kb/docs/`, `kb/errors/` and `kb/approved/` only. Both of these files name every route and mention the words the corpus is deliberately silent on, so loading either would poison retrieval and break the abstain examples.

**Scheme.** `doc_id` is `<area>-<slug>-<version>`. `route` carries the version prefix. `url` is `https://docs.example.com/<version>/<area>/<slug>`. Error table rows load as `<area>-errors#<CODE>`.

---

## Payments, 17 files

| doc_id | route | ver | status | The distinct fact |
|---|---|---|---|---|
| `payments-create-v2` | `/v2/payments` | v2 | current | `Idempotency-Key` is **optional**. A reused key is ignored and the request runs again, creating a second payment. Emits `payment.created` |
| `payments-create-v3` | `/v3/payments` | v3 | current | `Idempotency-Key` is **required**. Reuse with a different body returns `PAY_4090`. Keys retained 24 hours |
| `payments-get-v2` | `/v2/payments/{id}` | v2 | current | No `expand` parameter. The receipt comes from the separate `/v2/payments/{id}/receipt` route |
| `payments-get-v3` | `/v3/payments/{id}` | v3 | current | Adds `expand=receipt`, which inlines the receipt and replaces the deprecated receipt route |
| `payments-list-v2` | `/v2/payments` | v2 | current | **Offset** pagination. `offset` and `limit`, response has `total_count`. Max limit 100 |
| `payments-list-v3` | `/v3/payments` | v3 | current | **Cursor** pagination. `cursor` and `limit`, response has `next_cursor` and `has_more` and **no** `total_count` |
| `payments-capture-v2` | `/v2/payments/{id}/capture` | v2 | current | **Near-miss A.** Not the 3DS step. Confirm does not exist in v2, so authentication failures surface at capture time |
| `payments-capture-v3` | `/v3/payments/{id}/capture` | v3 | current | **Near-miss A.** Moves money. A payment still needing authentication returns `PAY_4030`, confirm it first. Emits `payment.captured` |
| `payments-confirm-v3` | `/v3/payments/{id}/confirm` | v3 | current | **Near-miss A.** New in v3. The 3DS authentication step, moves no money. Emits `payment.confirmed` |
| `payments-refund-v2` | `/v2/payments/{id}/refund` | v2 | current | **Near-miss B.** Refund window is **30 days** after capture, then `PAY_4013` |
| `payments-refund-v3` | `/v3/payments/{id}/refund` | v3 | current | **Near-miss B.** Refund window is **90 days** after capture. Refunding before `payment.captured` settles returns `PAY_4022` |
| `payments-reversal-v2` | `/v2/payments/{id}/reversal` | v2 | current | **Near-miss B.** Releases an authorization not yet captured. Already captured returns `PAY_4023` |
| `payments-reversal-v3` | `/v3/payments/{id}/reversal` | v3 | current | **Near-miss B.** Same, and it is the replacement for the deprecated void route. Emits `payment.reversed` |
| `payments-void-v2` | `/v2/payments/{id}/void` | v2 | current | Cancels an authorization in v2. The route that goes away in v3 |
| `payments-void-v3` | `/v3/payments/{id}/void` | v3 | **deprecated** | Removed in v3. `replaced_by: /v3/payments/{id}/reversal` |
| `payments-receipt-v2` | `/v2/payments/{id}/receipt` | v2 | current | Standalone receipt fetch in v2 |
| `payments-receipt-v3` | `/v3/payments/{id}/receipt` | v3 | **deprecated** | Removed in v3. `replaced_by: /v3/payments/{id}?expand=receipt` |

## Webhooks, 18 files

| doc_id | route | ver | status | The distinct fact |
|---|---|---|---|---|
| `webhooks-endpoints-create-v2` | `/v2/webhooks/endpoints` | v2 | current | `secret` is **not accepted**. Signing uses the **account-level** secret shared by every endpoint |
| `webhooks-endpoints-create-v3` | `/v3/webhooks/endpoints` | v3 | current | `secret` is **required** (`WHK_4010`). The signing key is returned **once** and never again. Signing is **per endpoint** |
| `webhooks-endpoints-list-v2` | `/v2/webhooks/endpoints` | v2 | current | Lists endpoints. Carries the v2 rate limits, sandbox 30/min and production **60**/min |
| `webhooks-endpoints-list-v3` | `/v3/webhooks/endpoints` | v3 | current | Lists endpoints. Carries the v3 rate limits, sandbox 30/min and production **600**/min |
| `webhooks-endpoints-delete-v2` | `/v2/webhooks/endpoints/{id}` | v2 | current | Deletes one endpoint, `WHK_4004` if unknown |
| `webhooks-endpoints-delete-v3` | `/v3/webhooks/endpoints/{id}` | v3 | current | Same in v3 |
| `webhooks-endpoints-test-v2` | `/v2/webhooks/endpoints/{id}/test` | v2 | current | Sends a synthetic event to **one** endpoint |
| `webhooks-endpoints-test-v3` | `/v3/webhooks/endpoints/{id}/test` | v3 | current | Same, and it is the replacement for the deprecated ping route |
| `webhooks-events-list-v2` | `/v2/webhooks/events` | v2 | current | **Near-miss C.** One row per **event**. Lists the five v2 event types, no `payment.confirmed` |
| `webhooks-events-list-v3` | `/v3/webhooks/events` | v3 | current | **Near-miss C.** One row per **event**. Lists six v3 event types including `payment.confirmed` |
| `webhooks-deliveries-list-v2` | `/v2/webhooks/deliveries` | v2 | current | **Near-miss C.** One row per **HTTP attempt**, many per event. Failed after 5 attempts is `WHK_4100` |
| `webhooks-deliveries-list-v3` | `/v3/webhooks/deliveries` | v3 | current | **Near-miss C.** Same, and states v3 signs with the per-endpoint secret where v2 signed with the account secret |
| `webhooks-deliveries-retry-v2` | `/v2/webhooks/deliveries/{id}/retry` | v2 | current | **Near-miss D.** One failed delivery, one endpoint. **No `backoff`**, the retry is immediate |
| `webhooks-deliveries-retry-v3` | `/v3/webhooks/deliveries/{id}/retry` | v3 | current | **Near-miss D.** Adds optional `backoff` of `immediate`, `linear`, or `exponential`, default `exponential` |
| `webhooks-events-replay-v2` | `/v2/webhooks/events/{id}/replay` | v2 | current | **Near-miss D.** Re-emits one event to **all** active endpoints, creating new deliveries |
| `webhooks-events-replay-v3` | `/v3/webhooks/events/{id}/replay` | v3 | current | **Near-miss D.** Same in v3 |
| `webhooks-ping-v2` | `/v2/webhooks/ping` | v2 | current | Pings **every** registered endpoint at once. The route that goes away in v3 |
| `webhooks-ping-v3` | `/v3/webhooks/ping` | v3 | **deprecated** | Removed in v3. `replaced_by: /v3/webhooks/endpoints/{id}/test`, called once per endpoint |

## Error tables, 2 files

Loaded as one `Doc` per row, `doc_id` `<area>-errors#<CODE>`, `version: all`, `route: ""`.

| doc_id | HTTP | The distinct fact |
|---|---|---|
| `payments-errors#PAY_4001` | 404 | Payment id not found |
| `payments-errors#PAY_4012` | 400 | Refund **amount** exceeds what was captured. Not the time window, that is `PAY_4013` |
| `payments-errors#PAY_4013` | 400 | Refund **window** expired. 30 days v2, 90 days v3. Not the amount, that is `PAY_4012` |
| `payments-errors#PAY_4022` | 422 | Payment not in a state that allows the operation |
| `payments-errors#PAY_4023` | 422 | Already captured, use refund instead of reversal |
| `payments-errors#PAY_4030` | 402 | **v3 only.** Needs 3DS, call confirm before capture |
| `payments-errors#PAY_4090` | 409 | **v3 only.** Idempotency key reused with a different body, keys retained 24 hours |
| `payments-errors#RATE_LIMITED` | 429 | Sandbox **30**/min both versions. Production **60**/min v2, **600**/min v3. Honor `Retry-After` |
| `webhooks-errors#WHK_4004` | 404 | Endpoint not found |
| `webhooks-errors#WHK_4009` | 409 | An endpoint with this url is already registered |
| `webhooks-errors#WHK_4010` | 400 | **v3 only.** `secret` required on endpoint create |
| `webhooks-errors#WHK_4100` | 502 | Unreachable after 5 attempts, delivery marked failed, use retry |
| `webhooks-errors#WHK_4220` | 400 | Signature mismatch. **v3 signs with the per-endpoint secret, v2 with the account secret** |
| `webhooks-errors#WHK_4221` | 400 | Signature timestamp outside the 5 minute tolerance window, check clock skew |
| `webhooks-errors#WHK_4290` | 409 | Delivery already succeeded, cannot retry. Use replay if the event must go again |
| `webhooks-errors#RATE_LIMITED` | 429 | Identical to the payments row |

## Approved answer seed, 1 file

| doc_id | source | route | ver | The distinct fact |
|---|---|---|---|---|
| `approved-seed-001` | `approved_answer` | `/v3/payments/{id}/refund` | v3 | A previously approved answer explaining the 90 day v3 refund window against `PAY_4013`. Exists so the cache demo has one hit before anything is approved live. Version pinned to v3. Evals set `use_cache=False` and must not see it |

---

## Near-miss pairs

| Pair | Docs | The sentence that separates them |
|---|---|---|
| **A** capture vs confirm | `payments-capture-v2`, `payments-capture-v3`, `payments-confirm-v3` | Capture moves the money on an already authenticated authorization. Confirm completes 3DS authentication and moves no money. Confirm is v3 only |
| **B** refund vs reversal | `payments-refund-v2/v3`, `payments-reversal-v2/v3` | Refund returns money on a payment that was **captured**. Reversal releases an authorization that was **never captured** |
| **C** events vs deliveries | `webhooks-events-list-v2/v3`, `webhooks-deliveries-list-v2/v3` | Events are one row per thing that happened. Deliveries are one row per HTTP attempt to send an event to an endpoint, many rows per event |
| **D** retry vs replay | `webhooks-deliveries-retry-v2/v3`, `webhooks-events-replay-v2/v3` | Retry re-sends **one** failed delivery to **one** endpoint. Replay re-emits an event to **all** active endpoints and creates new deliveries |

## Version differences a ticket can hinge on

| Difference | v2 | v3 | Docs |
|---|---|---|---|
| List pagination | offset, `total_count` | cursor, `next_cursor` and `has_more` | `payments-list-v2/v3` |
| Idempotency key | optional, reuse ignored | required, `PAY_4090` on mismatch | `payments-create-v2/v3` |
| Refund window | 30 days | 90 days | `payments-refund-v2/v3`, `payments-errors#PAY_4013` |
| Webhook signing secret | account level | per endpoint, returned once | `webhooks-endpoints-create-v2/v3`, `webhooks-errors#WHK_4220` |
| Retry backoff | none, immediate | `backoff` of `immediate`, `linear`, `exponential` | `webhooks-deliveries-retry-v2/v3` |
| Receipt | separate route | `expand=receipt` | `payments-get-v2/v3`, `payments-receipt-v3` |
| 3DS | does not exist | confirm route | `payments-confirm-v3` |
| Production rate limit | 60/min | 600/min | both `RATE_LIMITED` rows |

## Cross-area facts, for L2 synthesis

Payments emit `payment.created`, `payment.captured`, `payment.refunded`, `payment.reversed`, `payment.failed`, plus `payment.confirmed` in v3. The capture, refund and reversal docs each name the event they emit, and the events-list docs carry the full type list. Refunding before the `payment.captured` event settles returns `PAY_4022`.

## What the corpus deliberately does not cover

Nothing anywhere in `kb/` mentions service levels, cost, client libraries for any language, where data is stored geographically, or sending many operations in one request. Grep confirms zero hits for `SLA`, `pricing`, `price`, `SDK`, `data residency`, `residency`, `batch`, `bulk`, `GDPR`. The 6 abstain examples depend on this staying true.
