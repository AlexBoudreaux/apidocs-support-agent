---
doc_id: payments-create-v3
route: /v3/payments
version: v3
area: payments
status: current
replaced_by: null
description: How to create a payment in v3 and why the Idempotency-Key header is required on every create request.
url: https://docs.example.com/v3/payments/create
---

## POST /v3/payments

Creates a payment and returns the payment object. In v3 the `Idempotency-Key` header is required on every request to `/v3/payments`. Sending the same key again with a different request body returns `PAY_4090`. Keys are retained 24 hours, after which the same key may be used for a new payment.

### Request
| Field | Type | Required | Notes |
|---|---|---|---|
| `idempotency_key` | header | yes | Sent as the `Idempotency-Key` header. Required in v3. |
| `amount` | integer | yes | Smallest currency unit. |
| `currency` | string | yes | Three letter currency code. |
| `payment_method` | string | yes | Identifier of the stored or tokenized payment method. |
| `capture_method` | string | no | One of `automatic` or `manual`. Default `automatic`. |
| `metadata` | object | no | Free form key and value pairs. |

Create one request per payment. Rate limits in v3 are 30 requests per minute in sandbox and 600 requests per minute in production. Exceeding either returns `RATE_LIMITED`.

### Response
Returns the created payment with its current state.

```json
{
  "id": "pay_3Kd91xR2",
  "amount": 4200,
  "currency": "usd",
  "status": "requires_confirmation",
  "capture_method": "manual",
  "created_at": "2026-01-08T17:04:11Z"
}
```

A successful create emits the `payment.created` webhook event.

### Errors
`PAY_4090`, `PAY_4022`, `RATE_LIMITED`

### Example
```bash
curl -X POST https://api.example.com/v3/payments \
  -H "Authorization: Bearer sk_test_REDACTED" \
  -H "Idempotency-Key: 8f21c0de-4a77-4c11-9d2a-1b0e55d9a331" \
  -H "Content-Type: application/json" \
  -d '{"amount":4200,"currency":"usd","payment_method":"pm_9Jq2","capture_method":"manual"}'
```
