---
doc_id: payments-void-v2
route: /v2/payments/{id}/void
version: v2
area: payments
status: current
replaced_by: null
description: How to void a payment in v2 and how void differs from reversal
url: https://docs.example.com/v2/payments/void
---

## POST /v2/payments/{id}/void

Cancels a payment that has not moved money yet and marks it void so it can no longer be captured. Void is the terminal cancel action in v2 and applies to authorizations that are still open. It behaves like a reversal that also closes the payment to further operations, and a voided payment emits `payment.reversed`. A failed attempt emits `payment.failed`.

### Request
| Field | Type | Required | Notes |
|---|---|---|---|
| id | string | yes | Path parameter, the payment identifier |
| reason | string | no | Free text stored on the payment |
| metadata | object | no | Key value pairs merged into the payment |

### Response
Returns the payment in the void state.

```json
{
  "id": "pay_3Kd91xR2",
  "state": "void",
  "amount": 4500,
  "captured_amount": 0,
  "voided_at": "2024-03-11T10:11:07Z"
}
```

A payment that has already been captured cannot be voided and returns `PAY_4023`, since captured money is returned with `/v2/payments/{id}/refund`. A payment that is already void or otherwise ineligible returns `PAY_4022`. An unknown identifier returns `PAY_4001`. Calling `/v2/payments/{id}/void` twice is safe and the second call reports the state conflict rather than voiding again.

### Errors
`PAY_4023`, `PAY_4022`, `PAY_4001`

### Example
```bash
curl -X POST https://api.example.com/v2/payments/pay_3Kd91xR2/void \
  -H "Authorization: Bearer sk_test_REDACTED" \
  -H "Content-Type: application/json" \
  -d '{"reason":"duplicate_order"}'
```
