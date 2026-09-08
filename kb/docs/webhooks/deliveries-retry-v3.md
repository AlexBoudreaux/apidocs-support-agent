---
doc_id: webhooks-deliveries-retry-v3
route: /v3/webhooks/deliveries/{id}/retry
version: v3
area: webhooks
status: current
replaced_by: null
description: How to retry one failed webhook delivery to one endpoint in v3 and choose a backoff. This is not for re-emitting an event to all endpoints, for that use events-replay.
url: https://docs.example.com/v3/webhooks/deliveries-retry
---

## POST /v3/webhooks/deliveries/{id}/retry

Re-sends ONE failed delivery to ONE endpoint. It is not for re-emitting an event to all endpoints, so use events-replay when every active receiver needs the event again. Retry works only on a delivery whose status is failed, which happens after 5 attempts return `WHK_4100`. The new attempt is appended to the same delivery record rather than creating a new one.

### Request
| Field | Type | Required | Notes |
|---|---|---|---|
| id | string | yes | Path parameter, the delivery id such as whd_88fLz2 |
| backoff | string | no | One of immediate, linear, exponential. Defaults to exponential |

The `backoff` field is new in v3. In v2 there was no such field and the retry was always sent immediately.

### Response
Returns the delivery with its attempt counter advanced.

```json
{
  "id": "whd_88fLz2",
  "endpoint_id": "whe_71bQm4",
  "attempt": 6,
  "status": "pending",
  "backoff": "exponential"
}
```

### Errors
`WHK_4290`, `WHK_4004`, `WHK_4100`, `RATE_LIMITED`

Retrying a delivery that already succeeded returns `WHK_4290`.

### Example
```bash
curl -X POST https://api.example.com/v3/webhooks/deliveries/whd_88fLz2/retry \
  -H "Authorization: Bearer sk_test_REDACTED" \
  -H "Content-Type: application/json" \
  -d '{"backoff":"linear"}'
```
