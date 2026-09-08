---
doc_id: webhooks-events-replay-v2
route: /v2/webhooks/events/{id}/replay
version: v2
area: webhooks
status: current
replaced_by: null
description: How to replay one webhook event to all currently active endpoints in v2. This is not for re-sending a single failed delivery, for that use deliveries-retry.
url: https://docs.example.com/v2/webhooks/events-replay
---

## POST /v2/webhooks/events/{id}/replay

Re-emits one event to all currently active endpoints and creates new deliveries for each of them. Call `POST /v2/webhooks/events/{id}/replay` when you add an endpoint after the fact, or when a whole set of handlers missed a window of traffic. This route is not for re-sending a single failed delivery to one endpoint. For that, use the deliveries-retry route.

The replay uses the current endpoint list, not the one that existed when the event was first emitted. Endpoints registered since then receive the event, and endpoints that were deleted or set inactive do not. Deliveries are created one delivery at a time and appear in the delivery history with fresh ids. The original deliveries are left untouched.

### Request
| Field | Type | Required | Notes |
|---|---|---|---|
| id | string | yes | Path parameter, the event id such as evt_5Yq30a |

No request body is accepted.

### Response
Returns the event and the deliveries that were created.

```json
{
  "event_id": "evt_5Yq30a",
  "event_type": "payment.captured",
  "deliveries": [
    {
      "id": "whd_88fLz2",
      "endpoint_id": "whe_71bQm4",
      "status": "pending"
    }
  ],
  "delivery_count": 1
}
```

An unknown event id returns `WHK_4004`. Endpoints that stay unreachable after 5 attempts record `WHK_4100`.

### Errors
`WHK_4004`, `WHK_4100`, `RATE_LIMITED`

### Example
```bash
curl -X POST https://api.example.com/v2/webhooks/events/evt_5Yq30a/replay \
  -H "Authorization: Bearer sk_test_REDACTED"
```
