---
doc_id: webhooks-endpoints-list-v3
route: /v3/webhooks/endpoints
version: v3
area: webhooks
status: current
replaced_by: null
description: how to list the webhook endpoints registered on the account in v3 and page through them with a cursor
url: https://docs.example.com/v3/webhooks/endpoints-list
---

## GET /v3/webhooks/endpoints

Returns the webhook endpoints registered on the account, newest first. Use it to confirm which urls are active before you send a test event or replay an event. The listing never includes the signing key, which is shown only in the create response.

### Request
| Field | Type | Required | Notes |
|---|---|---|---|
| cursor | string | no | Opaque cursor from `next_cursor` on the previous page |
| limit | integer | no | Page size, max 100, defaults to 20 |
| active | boolean | no | Filter to active or inactive endpoints |

### Response
Cursor paginated. The body carries `next_cursor` and `has_more`.

```json
{
  "data": [
    {
      "id": "whe_71bQm4",
      "url": "https://merchant.example.com/hooks",
      "event_types": ["payment.captured"],
      "active": true,
      "created_at": "2026-04-02T10:15:00Z"
    }
  ],
  "next_cursor": "cur_9fTa20",
  "has_more": true
}
```

Rate limits apply to this route like every other one. Sandbox allows 30 requests per minute and production allows 600 requests per minute in v3. Going over either limit returns `RATE_LIMITED`, so page with a reasonable `limit` instead of many small pages.

### Errors
`RATE_LIMITED`

### Example
```bash
curl https://api.example.com/v3/webhooks/endpoints?limit=20 \
  -H "Authorization: Bearer sk_test_REDACTED"
```
