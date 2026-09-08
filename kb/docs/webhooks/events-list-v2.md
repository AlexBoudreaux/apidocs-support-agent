---
doc_id: webhooks-events-list-v2
route: /v2/webhooks/events
version: v2
area: webhooks
status: current
replaced_by: null
description: How to list the webhook events that happened in the account in v2. This is not the list of HTTP delivery attempts, for that use deliveries-list.
url: https://docs.example.com/v2/webhooks/events-list
---

## GET /v2/webhooks/events

Returns one row per event that happened in the account, such as a payment being captured or refunded. Use `GET /v2/webhooks/events` when you want to know what occurred, not how many times we tried to tell your server about it. This route is not the list of HTTP delivery attempts. For the attempts made against each endpoint, use the deliveries-list route, which returns many rows per event.

Events exist whether or not any endpoint is subscribed to them. The event id returned here is what you pass to the replay route.

The v2 event type names are:

```text
payment.created
payment.captured
payment.refunded
payment.reversed
payment.failed
```

### Request
| Field | Type | Required | Notes |
|---|---|---|---|
| event_type | string | no | Filter to one event type |
| created_after | string | no | ISO 8601 timestamp lower bound |
| offset | integer | no | Number of events to skip |
| limit | integer | no | Page size, maximum 100 |

### Response
A page of event objects with the account total.

```json
{
  "data": [
    {
      "id": "evt_5Yq30a",
      "event_type": "payment.captured",
      "payment_id": "pay_3Kd91xR2",
      "created_at": "2024-03-11T18:02:44Z"
    }
  ],
  "total_count": 412
}
```

### Errors
`RATE_LIMITED`, `WHK_4004`

### Example
```bash
curl "https://api.example.com/v2/webhooks/events?event_type=payment.captured&limit=20" \
  -H "Authorization: Bearer sk_test_REDACTED"
```
