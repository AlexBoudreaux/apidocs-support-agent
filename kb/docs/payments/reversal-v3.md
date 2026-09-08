---
doc_id: payments-reversal-v3
route: /v3/payments/{id}/reversal
version: v3
area: payments
status: current
replaced_by: null
description: How to release an authorization that has not been captured in v3 and how reversal differs from refund.
url: https://docs.example.com/v3/payments/reversal
---

## POST /v3/payments/{id}/reversal

Releases an authorization that has not been captured, freeing the held funds on the cardholder account. Reversal is not for returning money on a settled payment. Use `refund` at `/v3/payments/{id}/refund` for that. Calling `/v3/payments/{id}/reversal` on a payment that was already captured returns `PAY_4023`, which tells you to use refund instead.

### Request
| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | path | yes | Payment identifier of an authorized, uncaptured payment. |
| `amount` | integer | no | Smallest currency unit for a partial release. Defaults to the full authorized amount. |
| `reason` | string | no | Free text recorded on the reversal. |

Reverse one payment per request. A payment in a state that allows neither capture nor reversal returns `PAY_4022`.

### Response
Returns the reversal and the authorization amount still held.

```json
{
  "id": "rev_6Cn41m",
  "payment_id": "pay_3Kd91xR2",
  "amount": 4200,
  "currency": "usd",
  "status": "succeeded",
  "amount_still_authorized": 0
}
```

A successful reversal emits the `payment.reversed` webhook event.

### Errors
`PAY_4023`, `PAY_4022`, `PAY_4001`, `RATE_LIMITED`

### Example
```bash
curl -X POST https://api.example.com/v3/payments/pay_3Kd91xR2/reversal \
  -H "Authorization: Bearer sk_test_REDACTED" \
  -H "Content-Type: application/json" \
  -d '{"amount":4200}'
```
