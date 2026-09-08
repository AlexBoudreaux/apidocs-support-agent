---
doc_id: payments-receipt-v2
route: /v2/payments/{id}/receipt
version: v2
area: payments
status: current
replaced_by: null
description: How to fetch the receipt for a payment in v2 using the separate receipt route
url: https://docs.example.com/v2/payments/receipt
---

## GET /v2/payments/{id}/receipt

Returns the receipt for a payment, including the line items, the captured total, and any refunded amount. In v2 this is the only way to read a receipt, because `GET /v2/payments/{id}` has no `expand` parameter and never inlines the receipt object. Fetch the payment first, then call `/v2/payments/{id}/receipt` when you need the receipt detail. Reading a receipt emits no webhook event.

### Request
| Field | Type | Required | Notes |
|---|---|---|---|
| id | string | yes | Path parameter, the payment identifier |
| format | string | no | One of json or html, defaults to json |

### Response
Returns the receipt object for the payment.

```json
{
  "id": "rcp_20Xk7a",
  "payment_id": "pay_3Kd91xR2",
  "currency": "usd",
  "captured_amount": 4500,
  "refunded_amount": 1500,
  "line_items": [
    {
      "description": "Annual plan",
      "amount": 4500,
      "quantity": 1
    }
  ],
  "issued_at": "2024-03-11T09:20:45Z",
  "receipt_url": "https://receipts.example.com/rcp_20Xk7a"
}
```

A receipt exists only after the payment has been captured. Requesting one for an authorization that has not settled returns `PAY_4022`, and an unknown payment identifier returns `PAY_4001`.

### Errors
`PAY_4001`, `PAY_4022`, `RATE_LIMITED`

### Example
```bash
curl https://api.example.com/v2/payments/pay_3Kd91xR2/receipt \
  -H "Authorization: Bearer sk_test_REDACTED"
```
