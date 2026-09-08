---
doc_id: webhooks-endpoints-list-v2
route: /v2/webhooks/endpoints
version: v2
area: webhooks
status: current
replaced_by: null
description: How to list the webhook endpoints registered on an account in v2 and check which ones are still active.
url: https://docs.example.com/v2/webhooks/endpoints-list
---

## GET /v2/webhooks/endpoints

Returns every webhook endpoint registered on the account. Use `GET /v2/webhooks/endpoints` to audit which urls are subscribed to which event types and to find the endpoint id you need for a test, a delete, or a delivery lookup. Inactive endpoints are returned too, with `active` set to false.

The list uses offset pagination. Pass `offset` and `limit` as query parameters. The maximum `limit` is 100 and the response carries `total_count`.

Requests are limited to 30 requests per minute in sandbox and 60 requests per minute in production. Over that ceiling the call returns `RATE_LIMITED`.

### Request
| Field | Type | Required | Notes |
|---|---|---|---|
| offset | integer | no | Number of endpoints to skip, defaults to 0 |
| limit | integer | no | Page size, defaults to 20, maximum 100 |
| active | boolean | no | Filter to active or inactive endpoints |

### Response
A page of endpoint objects plus the total number of endpoints on the account.

```json
{
  "data": [
    {
      "id": "whe_71bQm4",
      "url": "https://merchant.example.com/hooks",
      "event_types": ["payment.captured"],
      "active": true
    }
  ],
  "total_count": 3
}
```

### Errors
`RATE_LIMITED`, `WHK_4004`

### Example
```bash
curl https://api.example.com/v2/webhooks/endpoints?offset=0&limit=20 \
  -H "Authorization: Bearer sk_test_REDACTED"
```
