---
doc_id: payments-capture-v2
route: /v2/payments/{id}/capture
version: v2
area: payments
status: current
replaced_by: null
description: How to capture an authorized payment in v2, and why this is not the 3DS authentication step, which is handled by confirm in v3 and does not exist in v2.
url: https://docs.example.com/v2/payments/capture
---

## POST /v2/payments/{id}/capture

Moves money on an authorization that is already authenticated. Capture is not the 3DS authentication step, and a confirm route does not exist in v2, so payments that still require authentication fail at capture time rather than at a separate step. A successful capture emits `payment.captured` once the capture settles, and a failed attempt emits `payment.failed`. Capture the full authorized amount or less, never more.

### Request
| Field | Type | Required | Notes |
|---|---|---|---|
| id | string | yes | Path parameter, the payment identifier |
| amount | integer | no | Minor units, defaults to the full authorized amount |
| metadata | object | no | Key value pairs merged into the payment |

### Response
Returns the updated payment with its captured amount and state.

```json
{
  "id": "pay_3Kd91xR2",
  "state": "captured",
  "amount": 4500,
  "captured_amount": 4500,
  "captured_at": "2024-03-11T09:20:41Z"
}
```

A payment that is already captured, already reversed, or still awaiting authentication returns `PAY_4022`. An unknown identifier returns `PAY_4001`. To release an authorization instead of capturing it, call `/v2/payments/{id}/reversal`.

### Errors
`PAY_4022`, `PAY_4001`, `RATE_LIMITED`

### Example
```bash
curl -X POST https://api.example.com/v2/payments/pay_3Kd91xR2/capture \
  -H "Authorization: Bearer sk_test_REDACTED" \
  -H "Content-Type: application/json" \
  -d '{"amount":4500}'
```
