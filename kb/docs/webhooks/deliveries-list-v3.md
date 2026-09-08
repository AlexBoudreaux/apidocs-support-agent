---
doc_id: webhooks-deliveries-list-v3
route: /v3/webhooks/deliveries
version: v3
area: webhooks
status: current
replaced_by: null
description: How to list webhook delivery attempts in v3, one row per HTTP attempt to one endpoint. This is not the list of events that happened, for that use events-list.
url: https://docs.example.com/v3/webhooks/deliveries-list
---

## GET /v3/webhooks/deliveries

Returns one row per HTTP attempt made to send one event to one endpoint, so a single event usually has many rows here. This is not the list of things that happened in the account, so use events-list for that. Filter by `event_id` to see every attempt for one event, or by `endpoint_id` to audit one receiver.

### Request
| Field | Type | Required | Notes |
|---|---|---|---|
| cursor | string | no | Opaque cursor from `next_cursor` |
| limit | integer | no | Page size, max 100, defaults to 20 |
| event_id | string | no | Filter to attempts for one event |
| endpoint_id | string | no | Filter to attempts for one endpoint |
| status | string | no | One of pending, succeeded, failed |

### Response
Cursor paginated with `next_cursor` and `has_more`.

```json
{
  "data": [
    {
      "id": "whd_88fLz2",
      "event_id": "evt_5Yq30a",
      "endpoint_id": "whe_71bQm4",
      "attempt": 5,
      "response_status": 500,
      "status": "failed"
    }
  ],
  "next_cursor": null,
  "has_more": false
}
```

A delivery is marked failed after 5 attempts and reports `WHK_4100`. Retry is how you send it again, one delivery at a time. Each attempt is signed with the per-endpoint secret returned once at create time, while v2 signed with the account secret, so a receiver checking against the wrong secret records `WHK_4220`.

### Errors
`WHK_4100`, `WHK_4220`, `RATE_LIMITED`

### Example
```bash
curl https://api.example.com/v3/webhooks/deliveries?event_id=evt_5Yq30a \
  -H "Authorization: Bearer sk_test_REDACTED"
```
