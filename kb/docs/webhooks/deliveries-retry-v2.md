---
doc_id: webhooks-deliveries-retry-v2
route: /v2/webhooks/deliveries/{id}/retry
version: v2
area: webhooks
status: current
replaced_by: null
description: How to retry one failed webhook delivery to one endpoint in v2. This is not for re-emitting an event to all endpoints, for that use events-replay.
url: https://docs.example.com/v2/webhooks/deliveries-retry
---

## POST /v2/webhooks/deliveries/{id}/retry

Re-sends one failed delivery to the one endpoint it was addressed to. Call `POST /v2/webhooks/deliveries/{id}/retry` after you fix a handler that returned an error, using the delivery id from the delivery list. This route is not for re-emitting an event to all endpoints. For that, use the events-replay route.

In v2 there is no `backoff` parameter. The retry is immediate, so the attempt is made as soon as the request is accepted. Only deliveries in the failed state can be retried. A delivery that already succeeded returns `WHK_4290`.

### Request
| Field | Type | Required | Notes |
|---|---|---|---|
| id | string | yes | Path parameter, the delivery id such as whd_88fLz2 |

No request body is accepted.

### Response
Returns the new attempt recorded against the same delivery.

```json
{
  "id": "whd_88fLz2",
  "event_id": "evt_5Yq30a",
  "endpoint_id": "whe_71bQm4",
  "attempt": 6,
  "response_status": 200,
  "status": "succeeded"
}
```

If the endpoint is still unreachable after 5 attempts the delivery stays failed with `WHK_4100`, and you can retry again once the handler is fixed.

### Errors
`WHK_4290`, `WHK_4100`, `WHK_4004`, `RATE_LIMITED`

### Example
```bash
curl -X POST https://api.example.com/v2/webhooks/deliveries/whd_88fLz2/retry \
  -H "Authorization: Bearer sk_test_REDACTED"
```
