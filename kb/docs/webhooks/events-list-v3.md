---
doc_id: webhooks-events-list-v3
route: /v3/webhooks/events
version: v3
area: webhooks
status: current
replaced_by: null
description: How to list the webhook events that happened in the account in v3, one row per event. This is not the list of HTTP delivery attempts, for that use deliveries-list.
url: https://docs.example.com/v3/webhooks/events-list
---

## GET /v3/webhooks/events

Returns one row per event that happened in the account, such as a payment being captured. This is not the list of HTTP delivery attempts made to your endpoints, so use deliveries-list when you want to see what was actually sent and whether it succeeded. One event can produce many delivery rows, one per active endpoint.

The v3 event type names are

```text
payment.created
payment.confirmed
payment.captured
payment.refunded
payment.reversed
payment.failed
```

### Request
| Field | Type | Required | Notes |
|---|---|---|---|
| cursor | string | no | Opaque cursor from `next_cursor` |
| limit | integer | no | Page size, max 100, defaults to 20 |
| event_type | string | no | Filter to one type name |
| created_after | string | no | ISO 8601 timestamp lower bound |

### Response
Cursor paginated with `next_cursor` and `has_more`.

```json
{
  "data": [
    {
      "id": "evt_5Yq30a",
      "type": "payment.captured",
      "payment_id": "pay_3Kd91xR2",
      "created_at": "2026-04-02T10:15:00Z"
    }
  ],
  "next_cursor": "cur_2mLp81",
  "has_more": false
}
```

Sandbox allows 30 requests per minute and production allows 600 requests per minute in v3. Exceeding either returns `RATE_LIMITED`.

### Errors
`RATE_LIMITED`

### Example
```bash
curl https://api.example.com/v3/webhooks/events?limit=20 \
  -H "Authorization: Bearer sk_test_REDACTED"
```
