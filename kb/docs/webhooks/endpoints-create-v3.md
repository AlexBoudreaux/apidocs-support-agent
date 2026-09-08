---
doc_id: webhooks-endpoints-create-v3
route: /v3/webhooks/endpoints
version: v3
area: webhooks
status: current
replaced_by: null
description: how to register a webhook endpoint in v3 and get the signing key that is returned only once on create
url: https://docs.example.com/v3/webhooks/endpoints-create
---

## POST /v3/webhooks/endpoints

Registers a url that receives webhook events for the account. In v3 the `secret` field is required on create, and the signing key derived from it is returned exactly once in the create response and never again. Store that key when you read the response, because there is no route that shows it later. Signatures on every delivery to this endpoint are computed with the per-endpoint secret, not with an account-level secret.

### Request
| Field | Type | Required | Notes |
|---|---|---|---|
| url | string | yes | https url that receives the POST body |
| secret | string | yes | Required in v3. Missing secret returns `WHK_4010` |
| event_types | array | no | Event type names to send. Omit to receive all types |
| description | string | no | Free text label shown in listings |
| active | boolean | no | Defaults to true |

### Response
Returns the endpoint object plus `signing_key`, which appears in this response only.

```json
{
  "id": "whe_71bQm4",
  "url": "https://merchant.example.com/hooks",
  "event_types": ["payment.captured", "payment.refunded"],
  "active": true,
  "signing_key": "whsec_returned_once",
  "created_at": "2026-04-02T10:15:00Z"
}
```

### Errors
`WHK_4010`, `WHK_4009`, `RATE_LIMITED`

Registering a url that already exists on the account returns `WHK_4009`. Delete the existing endpoint first if you want a fresh signing key.

### Example
```bash
curl -X POST https://api.example.com/v3/webhooks/endpoints \
  -H "Authorization: Bearer sk_test_REDACTED" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://merchant.example.com/hooks","secret":"whsec_seed_value"}'
```
