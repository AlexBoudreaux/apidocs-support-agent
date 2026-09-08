---
doc_id: webhooks-endpoints-test-v3
route: /v3/webhooks/endpoints/{id}/test
version: v3
area: webhooks
status: current
replaced_by: null
description: how to send a synthetic test event to one webhook endpoint in v3 and verify the signature it receives
url: https://docs.example.com/v3/webhooks/endpoints-test
---

## POST /v3/webhooks/endpoints/{id}/test

Sends a synthetic event to one endpoint so you can check that the url is reachable and that your signature check works. The event is generated for the test and does not appear in the account event listing. This route replaces the deprecated ping route, which fired at every endpoint at once, so call it once per endpoint id you want to exercise.

### Request
| Field | Type | Required | Notes |
|---|---|---|---|
| id | string | yes | Path parameter, the endpoint id such as whe_71bQm4 |
| event_type | string | no | Type name to simulate, defaults to payment.created |

### Response
Returns the delivery row created for the test attempt.

```json
{
  "delivery_id": "whd_88fLz2",
  "endpoint_id": "whe_71bQm4",
  "event_type": "payment.created",
  "response_status": 200,
  "status": "succeeded"
}
```

The test request is signed with the per-endpoint secret returned once when the endpoint was created. In v2 signatures were computed with the account secret shared by every endpoint. In v3 each endpoint signs with its own secret, so verifying a v3 test payload against an account secret returns `WHK_4220` on your side.

### Errors
`WHK_4004`, `WHK_4220`, `WHK_4221`, `RATE_LIMITED`

A timestamp older than the 5 minute tolerance window returns `WHK_4221`.

### Example
```bash
curl -X POST https://api.example.com/v3/webhooks/endpoints/whe_71bQm4/test \
  -H "Authorization: Bearer sk_test_REDACTED"
```
