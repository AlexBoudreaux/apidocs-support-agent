---
doc_id: payments-create-v2
route: /v2/payments
version: v2
area: payments
status: current
replaced_by: null
description: How to create a payment in v2 and whether the Idempotency-Key header is required
url: https://docs.example.com/v2/payments/create
---

## POST /v2/payments

Creates a payment and places an authorization on the payment method. Send one request per payment. A successful call to `/v2/payments` emits a `payment.created` webhook event, and a payment that later fails emits `payment.failed`. The `Idempotency-Key` header is optional in v2, and a reused key is ignored, so the request is processed again and a second payment is created.

### Request
| Field | Type | Required | Notes |
|---|---|---|---|
| amount | integer | yes | Minor units, greater than zero |
| currency | string | yes | Three letter code |
| payment_method_id | string | yes | Stored payment method to authorize |
| capture | boolean | no | Capture immediately, defaults to false |
| description | string | no | Free text shown on the receipt |
| metadata | object | no | Key value pairs echoed back on read |

Rate limits in v2 allow 30 requests per minute in sandbox and 60 requests per minute in production. Exceeding either returns `RATE_LIMITED`.

### Response
Returns the created payment with its identifier and state.

```json
{
  "id": "pay_3Kd91xR2",
  "amount": 4500,
  "currency": "usd",
  "state": "authorized",
  "captured_amount": 0,
  "created_at": "2024-03-11T09:14:02Z",
  "metadata": {}
}
```

### Errors
`PAY_4022`, `RATE_LIMITED`

### Example
```bash
curl -X POST https://api.example.com/v2/payments \
  -H "Authorization: Bearer sk_test_REDACTED" \
  -H "Content-Type: application/json" \
  -d '{"amount":4500,"currency":"usd","payment_method_id":"pm_84Jd2"}'
```
