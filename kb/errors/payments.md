---
doc_id: payments-errors
route: ""
version: all
area: payments
status: current
replaced_by: null
description: Error codes returned by the payments API, with cause and fix for each.
url: https://docs.example.com/errors/payments
---

## Payments error codes

| Code | HTTP | Message | Cause | Fix | Versions |
|---|---|---|---|---|---|
| `PAY_4001` | 404 | Payment not found | The payment id in the path does not exist on this account, returned by any payments route that takes an id such as `GET /v2/payments/{id}` and `GET /v3/payments/{id}`. | Check the `id` value against a listing from `GET /v2/payments` or `GET /v3/payments` and retry with an id that exists on the same account as the API key. | v2, v3 |
| `PAY_4012` | 400 | Refund amount exceeds captured amount | The `amount` field sent to `POST /v2/payments/{id}/refund` or `POST /v3/payments/{id}/refund` is larger than the amount captured on the payment, minus refunds already issued. This code is about the AMOUNT only and never about the refund time window, which is `PAY_4013`. | Read `amount_captured` and `amount_refunded` from `GET /v3/payments/{id}` and send a refund `amount` no greater than the difference. | v2, v3 |
| `PAY_4013` | 400 | Refund window expired | The payment was captured too long ago for a refund on `POST /v2/payments/{id}/refund` or `POST /v3/payments/{id}/refund`, where the window is 30 days after capture in v2 and 90 days after capture in v3. This code is about the time window only and never about the refund amount, which is `PAY_4012`. | Compare `captured_at` from `GET /v3/payments/{id}` against the 30 day v2 window or the 90 day v3 window, and settle anything outside it outside the payments API. | v2, v3 |
| `PAY_4022` | 422 | Payment is not in a state that allows this operation | The payment `status` does not permit the requested action, most often a refund sent to `POST /v3/payments/{id}/refund` before the capture has settled and the `payment.captured` event has been emitted. | Poll `GET /v3/payments/{id}` until `status` is `captured`, or wait for the `payment.captured` webhook event, then send the request again. | v2, v3 |
| `PAY_4023` | 422 | Payment already captured, use refund instead of reversal | A reversal was sent to `POST /v3/payments/{id}/reversal` for a payment that has already been captured, and reversal only releases an authorization that has not been captured yet. | Call `POST /v3/payments/{id}/refund` instead, because the payment was already captured and reversal only applies before capture. | v2, v3 |
| `PAY_4030` | 402 | Authentication required, confirm the payment first | The payment needs 3DS authentication before money can move, returned by `POST /v3/payments/{id}/capture` on a payment that has not completed the authentication step. | Call `POST /v3/payments/{id}/confirm` to finish 3DS authentication, then call `POST /v3/payments/{id}/capture`. | v3 |
| `PAY_4090` | 409 | Idempotency key reused with a different request body | An `Idempotency-Key` header value sent to `POST /v3/payments` was already used with a different request body, and v3 retains keys for 24 hours. | Send a new unique `Idempotency-Key` for the changed body, or resend the original body unchanged under the same key within the 24 hour retention period. | v3 |
| `RATE_LIMITED` | 429 | Too many requests | The API key exceeded its per minute request limit, and the sandbox limit is 30 requests per minute in both v2 and v3 while production allows 60 requests per minute in v2 and 600 requests per minute in v3, so the same traffic that passes in production can be limited in sandbox. | Honor the `Retry-After` response header before retrying, and lower request concurrency against sandbox to stay under 30 requests per minute. | v2, v3 |
