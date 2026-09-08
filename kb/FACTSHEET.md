# Corpus fact sheet

This is the contract the corpus was written against in session 4a2. Four subagents wrote the
route docs in parallel (payments v2, payments v3, webhooks v2, webhooks v3) and a fifth wrote the
error tables, each bound to this file verbatim so their facts could not drift apart. It is committed
so that anyone who later fixes a doc bug or adds a route has the same contract.

The corpus on disk is authoritative where the two ever disagree. `kb/CORPUS.md` is the index of what
was actually produced. Five near-miss descriptions were tightened after the writers finished so each
one names its sibling route, which is the only edit made outside the rules below.

Anyone editing `kb/docs/` must tell Alex, because eval reference answers cite these files.

---

## Rules the writers followed. BINDING for any later edit.

Written as instructions to the writers. Read them as the invariants the corpus holds to.

## File path and naming scheme

- Route docs: `kb/docs/<area>/<slug>-<version>.md`
- `doc_id` = `<area>-<slug>-<version>`  e.g. `payments-refund-v3`, `webhooks-endpoints-create-v2`
- `route` = version-prefixed path, e.g. `/v3/payments/{id}/refund`
- `url` = `https://docs.example.com/<version>/<area>/<slug>` e.g. `https://docs.example.com/v2/webhooks/endpoints-create`
- Path parameters are always `{id}`.

## Frontmatter, exact keys, exact order, YAML

```yaml
---
doc_id: payments-refund-v3
route: /v3/payments/{id}/refund
version: v3
area: payments
status: current
replaced_by: null
description: <one or two sentences, written as the sentence a developer would type into search>
url: https://docs.example.com/v3/payments/refund
---
```

- `status` is `current` except the three deprecated v3 files, which are `deprecated`.
- `replaced_by` is `null` except deprecated files, where it is the replacement route path string.
- No other keys. No quotes around values unless the value contains a `:` (descriptions often do NOT need quotes; if a description contains a colon, rewrite it to avoid the colon rather than quoting).

## Body shape, exact

```markdown
## <METHOD> <route>

One paragraph, 2 to 4 sentences, on what it does and when to use it. If this route is
half of a near-miss pair, this paragraph says what it is NOT for and names the sibling route.

### Request
| Field | Type | Required | Notes |
|---|---|---|---|
| ... | ... | ... | ... |

### Response
Short prose plus a fenced json block of the response body.

### Errors
`CODE_A`, `CODE_B`  (bare comma-separated codes, at least one, from the error code list below,
and only codes valid for this area and version)

### Example
```bash
curl ...
```
```

HARD RULES for every file:
- Body length 150 to 350 words (count words in the body only, excluding frontmatter). Aim 200-280.
- The body MUST contain its own route path (the version-prefixed one) at least once.
- The body MUST name at least one error code from the tables below.
- The curl example uses `https://api.example.com<route>` with `{id}` replaced by a literal id
  like `pay_3Kd91xR2` (payments) or `whe_71bQm4` (webhook endpoint) / `whd_88fLz2` (delivery) /
  `evt_5Yq30a` (event), and header `Authorization: Bearer sk_test_REDACTED`.
- Every request/response field name is snake_case.

## BANNED WORDS. Zero occurrences anywhere in any file you write.

`SLA`, `SLAs`, `pricing`, `price`, `priced`, `SDK`, `SDKs`, `data residency`, `residency`,
`batch`, `batches`, `batching`, `bulk`, `uptime guarantee`, `cost`, `billing`, `invoice`,
`Python`, `Java`, `Node`, `client library`, `region`, `regional`, `GDPR`, `EU-only`.

The eval set contains abstain examples that require the corpus to be silent on these.
If you need to describe many-at-once behavior, say "one request per payment" or
"one delivery at a time", never "batch".

Also do NOT invent facts about latency guarantees, support hours, contracts, or account tiers.

## Version-difference facts. These MUST appear in the text, verbatim in meaning.

| Fact | v2 says | v3 says |
|---|---|---|
| List pagination (`GET /payments`) | Offset pagination. `offset` and `limit` query params. Response has `total_count`. Max `limit` 100. | Cursor pagination. `cursor` and `limit` query params. Response has `next_cursor` and `has_more`, and NO `total_count`. Max `limit` 100. |
| Idempotency (`POST /payments`) | `Idempotency-Key` header is optional. Reused keys are ignored, the request is processed again. | `Idempotency-Key` header is REQUIRED. Reuse with a different body returns `PAY_4090`. Keys are retained 24 hours. |
| Refund window (`POST /payments/{id}/refund`) | A payment can be refunded up to 30 days after capture. After that, `PAY_4013`. | A payment can be refunded up to 90 days after capture. After that, `PAY_4013`. |
| Webhook signing secret | Signatures are computed with the account-level signing secret, shared by every endpoint. | Signatures are computed with the per-endpoint secret returned once when the endpoint is created. |
| Retry backoff (`POST /webhooks/deliveries/{id}/retry`) | No `backoff` parameter. Retry is immediate. | Adds an optional `backoff` body field, one of `immediate`, `linear`, `exponential`. Default `exponential`. |
| Expand receipt (`GET /payments/{id}`) | No `expand` parameter. | Adds `expand=receipt` query param, which inlines the receipt object. This replaces the deprecated receipt route. |
| Endpoint create secret | `secret` is not accepted. The account signing secret is used. | `secret` is required on create and the signing key is returned exactly once in the create response, never again. |
| 3DS confirm | Does not exist in v2. Payments requiring authentication fail at capture time. | `POST /v3/payments/{id}/confirm` exists for the 3DS authentication step. |
| Rate limits | Sandbox 30 requests per minute, production 60 requests per minute. | Sandbox 30 requests per minute, production 600 requests per minute. |

## Near-miss pairs. Each side's `description` says what it is NOT for and names the sibling.

- **Pair A**: `capture` vs `confirm` (payments). Capture moves money on an authorization that is
  already authenticated. Confirm completes 3DS authentication and does not move money. Confirm is v3 only,
  so the v2 capture file names confirm as not existing in v2.
- **Pair B**: `refund` vs `reversal` (payments). Refund returns money on a CAPTURED (settled) payment.
  Reversal releases an authorization that has NOT been captured.
- **Pair C**: `events-list` vs `deliveries-list` (webhooks). Events are what happened in the account,
  one row per event. Deliveries are the HTTP attempts made to send an event to one endpoint,
  many rows per event.
- **Pair D**: `deliveries-retry` vs `events-replay` (webhooks). Retry re-sends ONE failed delivery to
  ONE endpoint. Replay re-emits an event to ALL currently active endpoints, creating new deliveries.

## Deprecated routes. Three v3 files only.

| File | status | replaced_by | Body |
|---|---|---|---|
| `payments/void-v3.md` | deprecated | `/v3/payments/{id}/reversal` | One paragraph only: removed in v3, what to use instead, and how the call maps. No Request/Response/Example sections. Keep an `### Errors` line. 150-250 words. |
| `payments/receipt-v3.md` | deprecated | `/v3/payments/{id}?expand=receipt` | Same shape. |
| `webhooks/ping-v3.md` | deprecated | `/v3/webhooks/endpoints/{id}/test` | Same shape. |

Their v2 counterparts (`void-v2`, `receipt-v2`, `ping-v2`) are normal `status: current` files with the full body shape.

## Cross-area facts. Needed for L2 synthesis eval examples. Put these in.

- Payments emit webhook events: `payment.created`, `payment.captured`, `payment.refunded`,
  `payment.reversed`, `payment.failed`. In v3 also `payment.confirmed`.
- The payments `capture`, `refund`, and `reversal` docs each say which event they emit.
- The webhooks `events-list` doc lists those event type names in a fenced block.
- `payment.captured` is emitted after capture settles, which is why a refund attempted before that
  event arrives returns `PAY_4022`.

## Error codes. Use only these. Do not invent new codes.

**Payments** (`kb/errors/payments.md`)
| Code | HTTP | Meaning | Versions |
|---|---|---|---|
| PAY_4001 | 404 | Payment not found | v2, v3 |
| PAY_4012 | 400 | Refund amount exceeds captured amount | v2, v3 |
| PAY_4013 | 400 | Refund window expired (30 days v2, 90 days v3) | v2, v3 |
| PAY_4022 | 422 | Payment is not in a state that allows this operation | v2, v3 |
| PAY_4023 | 422 | Payment already captured, use refund instead of reversal | v2, v3 |
| PAY_4030 | 402 | Authentication required, confirm the payment first | v3 |
| PAY_4090 | 409 | Idempotency key reused with a different request body | v3 |
| RATE_LIMITED | 429 | Too many requests | v2, v3 |

**Webhooks** (`kb/errors/webhooks.md`)
| Code | HTTP | Meaning | Versions |
|---|---|---|---|
| WHK_4004 | 404 | Webhook endpoint not found | v2, v3 |
| WHK_4009 | 409 | An endpoint with this url is already registered | v2, v3 |
| WHK_4010 | 400 | Endpoint secret is required on create | v3 |
| WHK_4100 | 502 | Endpoint unreachable after 5 attempts, delivery marked failed, use retry | v2, v3 |
| WHK_4220 | 400 | Signature mismatch (v3 signs with the per-endpoint secret, v2 with the account secret) | v2, v3 |
| WHK_4221 | 400 | Signature timestamp outside the 5 minute tolerance window | v2, v3 |
| WHK_4290 | 409 | Delivery already succeeded and cannot be retried | v2, v3 |
| RATE_LIMITED | 429 | Too many requests | v2, v3 |

Rule: a v2 file may only cite v2 codes. `PAY_4030` and `PAY_4090` and `WHK_4010` are v3 only.

## Route inventory

**Payments** (`kb/docs/payments/`)
| Slug | Method | Path (no version prefix) | v2 file | v3 file |
|---|---|---|---|---|
| create | POST | `/payments` | yes | yes |
| get | GET | `/payments/{id}` | yes | yes |
| list | GET | `/payments` | yes | yes |
| capture | POST | `/payments/{id}/capture` | yes | yes |
| confirm | POST | `/payments/{id}/confirm` | NO | yes |
| refund | POST | `/payments/{id}/refund` | yes | yes |
| reversal | POST | `/payments/{id}/reversal` | yes | yes |
| void | POST | `/payments/{id}/void` | yes | yes (deprecated) |
| receipt | GET | `/payments/{id}/receipt` | yes | yes (deprecated) |

17 payments files.

**Webhooks** (`kb/docs/webhooks/`)
| Slug | Method | Path | v2 file | v3 file |
|---|---|---|---|---|
| endpoints-create | POST | `/webhooks/endpoints` | yes | yes |
| endpoints-list | GET | `/webhooks/endpoints` | yes | yes |
| endpoints-delete | DELETE | `/webhooks/endpoints/{id}` | yes | yes |
| endpoints-test | POST | `/webhooks/endpoints/{id}/test` | yes | yes |
| events-list | GET | `/webhooks/events` | yes | yes |
| deliveries-list | GET | `/webhooks/deliveries` | yes | yes |
| deliveries-retry | POST | `/webhooks/deliveries/{id}/retry` | yes | yes |
| events-replay | POST | `/webhooks/events/{id}/replay` | yes | yes |
| ping | POST | `/webhooks/ping` | yes | yes (deprecated) |

18 webhooks files.

## Style

Plain, factual API reference prose. Short sentences. No marketing. No em dashes, no colons used
as sentence connectors. Do not write "Note:" or "Important:". Just state the fact.
