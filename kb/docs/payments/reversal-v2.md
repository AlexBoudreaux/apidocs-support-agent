---
doc_id: payments-reversal-v2
route: /v2/payments/{id}/reversal
version: v2
area: payments
status: current
replaced_by: null
description: How to release an uncaptured authorization in v2, not for returning money on a captured payment which uses refund
url: https://docs.example.com/v2/payments/reversal
---

## POST /v2/payments/{id}/reversal

Releases an authorization that has not been captured, freeing the held funds on the payment method. This route is not for returning money on a captured payment. Once a payment has settled, call `/v2/payments/{id}/refund` instead. A successful reversal emits `payment.reversed`, and a failed attempt emits `payment.failed`. Send one request per payment.

### Request
| Field | Type | Required | Notes |
|---|---|---|---|
| id | string | yes | Path parameter, the payment identifier |
| reason | string | no | Free text stored on the reversal |
| metadata | object | no | Key value pairs merged into the payment |

A reversal always releases the full remaining authorization. Partial reversal is not supported in v2.

### Response
Returns the updated payment in the reversed state.

```json
{
  "id": "pay_3Kd91xR2",
  "state": "reversed",
  "amount": 4500,
  "captured_amount": 0,
  "reversed_at": "2024-03-11T10:05:18Z"
}
```

Calling `/v2/payments/{id}/reversal` on a payment that is already captured returns `PAY_4023`, which means the payment must be refunded rather than reversed. A payment in any other state that forbids the operation returns `PAY_4022`, and an unknown identifier returns `PAY_4001`.

### Errors
`PAY_4023`, `PAY_4022`, `PAY_4001`

### Example
```bash
curl -X POST https://api.example.com/v2/payments/pay_3Kd91xR2/reversal \
  -H "Authorization: Bearer sk_test_REDACTED" \
  -H "Content-Type: application/json" \
  -d '{"reason":"customer_cancelled"}'
```
