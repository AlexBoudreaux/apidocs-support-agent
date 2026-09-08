---
doc_id: payments-get-v2
route: /v2/payments/{id}
version: v2
area: payments
status: current
replaced_by: null
description: How to retrieve a single payment by id in v2 and how to get its receipt
url: https://docs.example.com/v2/payments/get
---

## GET /v2/payments/{id}

Retrieves one payment by its identifier, including its current state, captured amount, and metadata. Use it to check whether an authorization has been captured, refunded, or reversed. There is no `expand` parameter in v2, so `/v2/payments/{id}` never inlines the receipt object. In v2 the receipt is fetched from the separate receipt route at `/v2/payments/{id}/receipt`.

### Request
| Field | Type | Required | Notes |
|---|---|---|---|
| id | string | yes | Path parameter, the payment identifier |

No query parameters are accepted.

### Response
Returns the payment object. The `receipt_id` field points at the receipt route.

```json
{
  "id": "pay_3Kd91xR2",
  "amount": 4500,
  "currency": "usd",
  "state": "captured",
  "captured_amount": 4500,
  "refunded_amount": 0,
  "receipt_id": "rcp_20Xk7a",
  "created_at": "2024-03-11T09:14:02Z",
  "captured_at": "2024-03-11T09:20:41Z",
  "metadata": {}
}
```

An unknown identifier returns `PAY_4001`. Reading a payment does not emit a webhook event, so poll this route or listen for `payment.captured` and `payment.failed` instead of retrying in a tight loop.

### Errors
`PAY_4001`, `RATE_LIMITED`

### Example
```bash
curl https://api.example.com/v2/payments/pay_3Kd91xR2 \
  -H "Authorization: Bearer sk_test_REDACTED"
```
