---
doc_id: payments-refund-v2
route: /v2/payments/{id}/refund
version: v2
area: payments
status: current
replaced_by: null
description: How to refund a captured payment in v2, not for reversing an uncaptured authorization which uses reversal
url: https://docs.example.com/v2/payments/refund
---

## POST /v2/payments/{id}/refund

Returns money on a payment that has already been captured and settled. This route is not for reversing an uncaptured authorization. To release an authorization that was never captured, call `/v2/payments/{id}/reversal` instead. A successful refund emits `payment.refunded`, and a failed attempt emits `payment.failed`. Send one request per payment, and issue several partial refunds by calling `/v2/payments/{id}/refund` more than once.

### Request
| Field | Type | Required | Notes |
|---|---|---|---|
| id | string | yes | Path parameter, the payment identifier |
| amount | integer | no | Minor units, defaults to the remaining captured amount |
| reason | string | no | Free text stored on the refund |
| metadata | object | no | Key value pairs stored on the refund |

### Response
Returns the refund and the updated refunded total on the payment.

```json
{
  "id": "ref_9Pm42t",
  "payment_id": "pay_3Kd91xR2",
  "amount": 1500,
  "state": "succeeded",
  "refunded_amount": 1500,
  "created_at": "2024-03-12T11:02:55Z"
}
```

In v2 a payment can be refunded up to 30 days after capture. After that window the call returns `PAY_4013`. Refunding more than was captured returns `PAY_4012`, and refunding before the `payment.captured` event arrives returns `PAY_4022`.

### Errors
`PAY_4013`, `PAY_4012`, `PAY_4022`, `PAY_4001`

### Example
```bash
curl -X POST https://api.example.com/v2/payments/pay_3Kd91xR2/refund \
  -H "Authorization: Bearer sk_test_REDACTED" \
  -H "Content-Type: application/json" \
  -d '{"amount":1500}'
```
