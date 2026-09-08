---
doc_id: webhooks-endpoints-delete-v2
route: /v2/webhooks/endpoints/{id}
version: v2
area: webhooks
status: current
replaced_by: null
description: How to delete a webhook endpoint in v2 and what happens to deliveries that were already queued for it.
url: https://docs.example.com/v2/webhooks/endpoints-delete
---

## DELETE /v2/webhooks/endpoints/{id}

Removes a registered webhook endpoint from the account. Call `DELETE /v2/webhooks/endpoints/{id}` when a destination url is retired so no further events are sent to it. Deletion is permanent, and the same url can be registered again afterwards with a new endpoint id.

Deliveries already recorded for the endpoint stay in the delivery history and can still be read. They are not attempted again, and a failed delivery that belonged to a deleted endpoint cannot be retried. If you only want to pause traffic, set `active` to false on the endpoint instead of deleting it.

### Request
| Field | Type | Required | Notes |
|---|---|---|---|
| id | string | yes | Path parameter, the endpoint id such as whe_71bQm4 |

No request body is accepted. Endpoints are removed one at a time, so delete each retired url with its own request.

### Response
Returns the deleted endpoint id and a confirmation flag. The response is the same whether the endpoint was active or already paused.

```json
{
  "id": "whe_71bQm4",
  "deleted": true,
  "deleted_at": "2024-03-14T09:31:07Z"
}
```

Deleting an endpoint that does not exist, or one that was already deleted, returns `WHK_4004`.

### Errors
`WHK_4004`, `RATE_LIMITED`

### Example
```bash
curl -X DELETE https://api.example.com/v2/webhooks/endpoints/whe_71bQm4 \
  -H "Authorization: Bearer sk_test_REDACTED"
```
