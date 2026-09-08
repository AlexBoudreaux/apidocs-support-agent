---
doc_id: webhooks-deliveries-list-v2
route: /v2/webhooks/deliveries
version: v2
area: webhooks
status: current
replaced_by: null
description: How to list webhook delivery attempts in v2. This is not the list of events that happened, for that use events-list.
url: https://docs.example.com/v2/webhooks/deliveries-list
---

## GET /v2/webhooks/deliveries

Returns one row per HTTP attempt to send one event to one endpoint. Because the same event is sent to every subscribed endpoint and is attempted again after a failure, you will see many rows per event. Use `GET /v2/webhooks/deliveries` to debug why a handler is not receiving traffic. This route is not the list of events that happened in the account. For that, use the events-list route, which returns one row per event.

A delivery is marked failed after 5 attempts and reports `WHK_4100`. Retry is how you re-send it, using the delivery id returned here. If your handler rejects the signature, the delivery records `WHK_4220`. In v2 signatures are computed with the account-level signing secret, shared by every endpoint, so verify against the account secret rather than a per-endpoint one.

### Request
| Field | Type | Required | Notes |
|---|---|---|---|
| event_id | string | no | Filter to attempts for one event |
| endpoint_id | string | no | Filter to attempts against one endpoint |
| status | string | no | One of pending, succeeded, failed |
| offset | integer | no | Number of deliveries to skip |
| limit | integer | no | Page size, maximum 100 |

### Response
A page of delivery objects with the total.

```json
{
  "data": [
    {
      "id": "whd_88fLz2",
      "event_id": "evt_5Yq30a",
      "endpoint_id": "whe_71bQm4",
      "attempt": 5,
      "response_status": 502,
      "status": "failed"
    }
  ],
  "total_count": 27
}
```

### Errors
`WHK_4100`, `WHK_4220`, `RATE_LIMITED`

### Example
```bash
curl "https://api.example.com/v2/webhooks/deliveries?event_id=evt_5Yq30a" \
  -H "Authorization: Bearer sk_test_REDACTED"
```
