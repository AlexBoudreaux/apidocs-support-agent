---
doc_id: webhooks-endpoints-test-v2
route: /v2/webhooks/endpoints/{id}/test
version: v2
area: webhooks
status: current
replaced_by: null
description: How to send a synthetic test event to one webhook endpoint in v2 to check that the url responds and the signature verifies.
url: https://docs.example.com/v2/webhooks/endpoints-test
---

## POST /v2/webhooks/endpoints/{id}/test

Sends a synthetic event to one endpoint so you can confirm the url is reachable and your signature check works. `POST /v2/webhooks/endpoints/{id}/test` targets a single endpoint identified in the path. To send a synthetic ping to every registered endpoint at once, use the ping route instead.

The test payload is signed the same way as real traffic. In v2 signatures are computed with the account-level signing secret, shared by every endpoint, so verify the test request against that account secret. A mismatch reported by your handler, or a signature your handler rejects, surfaces as `WHK_4220`. A signature whose timestamp is more than 5 minutes old returns `WHK_4221`.

### Request
| Field | Type | Required | Notes |
|---|---|---|---|
| id | string | yes | Path parameter, the endpoint id |
| event_type | string | no | Event type to simulate, defaults to payment.created |

### Response
Returns the synthetic delivery that was created, including the status code your url returned.

```json
{
  "delivery_id": "whd_88fLz2",
  "endpoint_id": "whe_71bQm4",
  "event_type": "payment.created",
  "response_status": 200,
  "succeeded": true
}
```

### Errors
`WHK_4004`, `WHK_4220`, `WHK_4221`, `RATE_LIMITED`

### Example
```bash
curl -X POST https://api.example.com/v2/webhooks/endpoints/whe_71bQm4/test \
  -H "Authorization: Bearer sk_test_REDACTED" \
  -H "Content-Type: application/json" \
  -d '{"event_type":"payment.captured"}'
```
