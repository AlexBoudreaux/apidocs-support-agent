---
doc_id: webhooks-errors
route: ""
version: all
area: webhooks
status: current
replaced_by: null
description: Error codes returned by the webhooks API, with cause and fix for each.
url: https://docs.example.com/errors/webhooks
---

## Webhooks error codes

| Code | HTTP | Message | Cause | Fix | Versions |
|---|---|---|---|---|---|
| `WHK_4004` | 404 | Webhook endpoint not found | The endpoint id in the path does not exist on this account, returned by routes such as `DELETE /v3/webhooks/endpoints/{id}` and `POST /v3/webhooks/endpoints/{id}/test`. | List endpoints with `GET /v3/webhooks/endpoints` and retry with an `id` that appears there for the same account as the API key. | v2, v3 |
| `WHK_4009` | 409 | An endpoint with this url is already registered | The `url` sent to `POST /v2/webhooks/endpoints` or `POST /v3/webhooks/endpoints` is already registered on the account, and each url may be registered once. | Find the existing endpoint with `GET /v3/webhooks/endpoints`, then reuse it or delete it with `DELETE /v3/webhooks/endpoints/{id}` before creating a new one on the same `url`. | v2, v3 |
| `WHK_4010` | 400 | Endpoint secret is required on create | The `secret` field was missing from the body of `POST /v3/webhooks/endpoints`, where it is required. | Send a `secret` in the `POST /v3/webhooks/endpoints` body and store the signing key from the create response, because it is returned exactly once and never again. | v3 |
| `WHK_4100` | 502 | Endpoint unreachable after 5 attempts | The receiving endpoint did not accept the delivery after 5 attempts, so the delivery was marked failed and appears with a failed status in `GET /v3/webhooks/deliveries`. | Fix the receiving endpoint so it returns a 2xx response, then re-send that one delivery with `POST /v3/webhooks/deliveries/{id}/retry`. | v2, v3 |
| `WHK_4220` | 400 | Signature mismatch | The signature computed by the receiver did not match the signature on the delivery, and v3 signs with the per-endpoint secret returned once at endpoint creation while v2 signs with the account-level signing secret shared by every endpoint. | Verify with the per-endpoint secret from the `POST /v3/webhooks/endpoints` create response on v3, or with the account-level signing secret on v2, and compute the signature over the exact raw request body before any parsing. | v2, v3 |
| `WHK_4221` | 400 | Signature timestamp outside tolerance window | The timestamp in the signature header on a delivery from the webhooks API is outside the 5 minute tolerance window compared to the receiver clock. | Correct clock skew on the receiving host by syncing it to a network time source, and verify signatures as soon as the request arrives rather than after queuing. | v2, v3 |
| `WHK_4290` | 409 | Delivery already succeeded and cannot be retried | `POST /v3/webhooks/deliveries/{id}/retry` was called on a delivery that already succeeded, and only a failed delivery can be retried. | Confirm the delivery status with `GET /v3/webhooks/deliveries`, and if the event genuinely needs re-sending use `POST /v3/webhooks/events/{id}/replay`, which re-emits the event to all currently active endpoints. | v2, v3 |
| `RATE_LIMITED` | 429 | Too many requests | The API key exceeded its per minute request limit, and the sandbox limit is 30 requests per minute in both v2 and v3 while production allows 60 requests per minute in v2 and 600 requests per minute in v3, so the same traffic that passes in production can be limited in sandbox. | Honor the `Retry-After` response header before retrying, and lower request concurrency against sandbox to stay under 30 requests per minute. | v2, v3 |
