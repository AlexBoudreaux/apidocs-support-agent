---
doc_id: payments-refund-v3
route: /v3/payments/{id}/refund
version: v3
area: payments
status: current
replaced_by: null
description: How to refund a captured payment in v3, including the 90 day refund window and how refund differs from reversal.
url: https://docs.example.com/v3/payments/refund
---

## POST /v3/payments/{id}/refund

Returns money on a payment that has already been captured and settled. Refund is not for reversing an uncaptured authorization. Use `reversal` at `/v3/payments/{id}/reversal` for that. In v3 a payment can be refunded up to 90 days after capture, and a later attempt on `/v3/payments/{id}/refund` returns `PAY_4013`.

### Request
| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | path | yes | Payment identifier of a captured payment. |
| `amount` | integer | no | Smallest currency unit. Defaults to the full captured amount. |
| `reason` | string | no | One of `duplicate`, `fraudulent`, or `requested_by_customer`. |
| `metadata` | object | no | Free form key and value pairs. |

Refunding more than was captured returns `PAY_4012`. Refunding before the `payment.captured` event has settled returns `PAY_4022`, so wait for that event before calling refund.

### Response
Returns the refund with the remaining refundable amount on the payment.

```json
{
  "id": "ref_2Bp70k",
  "payment_id": "pay_3Kd91xR2",
  "amount": 4200,
  "currency": "usd",
  "status": "succeeded",
  "amount_refundable_remaining": 0
}
```

A successful refund emits the `payment.refunded` webhook event.

### Errors
`PAY_4013`, `PAY_4012`, `PAY_4022`, `PAY_4001`, `RATE_LIMITED`

### Example
```bash
curl -X POST https://api.example.com/v3/payments/pay_3Kd91xR2/refund \
  -H "Authorization: Bearer sk_test_REDACTED" \
  -H "Content-Type: application/json" \
  -d '{"amount":4200,"reason":"requested_by_customer"}'
```
