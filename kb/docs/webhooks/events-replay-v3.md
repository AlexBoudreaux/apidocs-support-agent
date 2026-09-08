---
doc_id: webhooks-events-replay-v3
route: /v3/webhooks/events/{id}/replay
version: v3
area: webhooks
status: current
replaced_by: null
description: How to replay one webhook event to all currently active endpoints in v3. This is not for re-sending a single failed delivery, for that use deliveries-retry.
url: https://docs.example.com/v3/webhooks/events-replay
---

## POST /v3/webhooks/events/{id}/replay

Re-emits one event to ALL currently active endpoints and creates a new delivery for each of them. It is not for re-sending a single failed delivery, so use deliveries-retry when only one endpoint missed the event. The endpoint set is resolved when you call replay, so an endpoint registered after the original event still receives the replayed copy, and a deleted endpoint does not.

### Request
| Field | Type | Required | Notes |
|---|---|---|---|
| id | string | yes | Path parameter, the event id such as evt_5Yq30a |
| endpoint_ids | array | no | Restrict the replay to these active endpoint ids |

### Response
Returns the event id and the delivery rows that were created, one delivery at a time in the order the endpoints were resolved.

```json
{
  "event_id": "evt_5Yq30a",
  "type": "payment.captured",
  "deliveries": [
    {"id": "whd_88fLz2", "endpoint_id": "whe_71bQm4", "status": "pending"}
  ]
}
```

Each replayed delivery is signed with the per-endpoint secret for its endpoint. A receiver that checks the signature against the wrong secret records `WHK_4220`.

### Errors
`WHK_4004`, `WHK_4220`, `RATE_LIMITED`

An `endpoint_ids` entry that does not exist returns `WHK_4004`.

### Example
```bash
curl -X POST https://api.example.com/v3/webhooks/events/evt_5Yq30a/replay \
  -H "Authorization: Bearer sk_test_REDACTED"
```
