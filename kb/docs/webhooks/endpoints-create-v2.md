---
doc_id: webhooks-endpoints-create-v2
route: /v2/webhooks/endpoints
version: v2
area: webhooks
status: current
replaced_by: null
description: How to register a new webhook endpoint url in v2 and why the create call does not accept a secret field.
url: https://docs.example.com/v2/webhooks/endpoints-create
---

## POST /v2/webhooks/endpoints

Registers a url that receives webhook events for the account. Call `POST /v2/webhooks/endpoints` once per destination url, then subscribe it to the event types you care about. Each url may be registered once per account.

In v2 the create call does not accept a `secret` field. Signatures are computed with the account-level signing secret, shared by every endpoint, so every endpoint you register verifies against that same secret. Read the account signing secret from the dashboard and use it in your verification code.

### Request
| Field | Type | Required | Notes |
|---|---|---|---|
| url | string | yes | HTTPS destination that receives the POST |
| event_types | array | yes | Event type names to subscribe, such as payment.captured |
| description | string | no | Free text label for the endpoint |
| active | boolean | no | Defaults to true |

### Response
Returns the created endpoint object. No signing key is returned, because the account signing secret is used.

```json
{
  "id": "whe_71bQm4",
  "url": "https://merchant.example.com/hooks",
  "event_types": ["payment.captured", "payment.refunded"],
  "active": true,
  "created_at": "2024-03-11T18:02:44Z"
}
```

### Errors
`WHK_4009`, `WHK_4220`, `RATE_LIMITED`

### Example
```bash
curl -X POST https://api.example.com/v2/webhooks/endpoints \
  -H "Authorization: Bearer sk_test_REDACTED" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://merchant.example.com/hooks","event_types":["payment.captured"]}'
```
