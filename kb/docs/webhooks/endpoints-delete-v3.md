---
doc_id: webhooks-endpoints-delete-v3
route: /v3/webhooks/endpoints/{id}
version: v3
area: webhooks
status: current
replaced_by: null
description: how to delete a webhook endpoint in v3 and what happens to deliveries that are still queued for it
url: https://docs.example.com/v3/webhooks/endpoints-delete
---

## DELETE /v3/webhooks/endpoints/{id}

Removes a webhook endpoint from the account. Once the endpoint is deleted it stops receiving events, queued deliveries for it are dropped, and its per-endpoint signing key is destroyed. Deletion is permanent, so recreate the url with a new `secret` if you need it back. Use it when a receiver is retired or when you want to rotate a signing key, since the key is only ever issued at create time.

### Request
| Field | Type | Required | Notes |
|---|---|---|---|
| id | string | yes | Path parameter, the endpoint id such as whe_71bQm4 |

No request body is accepted.

### Response
Returns the deleted endpoint id and a confirmation flag.

```json
{
  "id": "whe_71bQm4",
  "deleted": true,
  "deleted_at": "2026-04-09T18:22:11Z"
}
```

Delivery rows already written for this endpoint stay readable in the deliveries listing. They cannot be retried, because there is no endpoint left to send them to.

### Errors
`WHK_4004`, `RATE_LIMITED`

An unknown or already deleted endpoint id returns `WHK_4004`.

### Example
```bash
curl -X DELETE https://api.example.com/v3/webhooks/endpoints/whe_71bQm4 \
  -H "Authorization: Bearer sk_test_REDACTED"
```
