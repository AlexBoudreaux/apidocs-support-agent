---
doc_id: payments-get-v3
route: /v3/payments/{id}
version: v3
area: payments
status: current
replaced_by: null
description: How to retrieve a single payment in v3 and how to inline the receipt with the expand query parameter.
url: https://docs.example.com/v3/payments/get
---

## GET /v3/payments/{id}

Retrieves one payment by its identifier. v3 adds the `expand=receipt` query parameter, which inlines the full receipt object in the response. That parameter replaces the deprecated receipt route, so a request to `/v3/payments/{id}?expand=receipt` returns everything the old receipt call returned.

### Request
| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | path | yes | Payment identifier, for example `pay_3Kd91xR2`. |
| `expand` | query | no | Set to `receipt` to inline the receipt object. Omit for the plain payment. |

### Response
Returns the payment. When `expand=receipt` is set, a `receipt` object is included with the line items and the settled totals.

```json
{
  "id": "pay_3Kd91xR2",
  "amount": 4200,
  "currency": "usd",
  "status": "captured",
  "captured_at": "2026-01-08T17:09:52Z",
  "receipt": {
    "receipt_number": "rc_44812",
    "issued_at": "2026-01-08T17:09:55Z",
    "amount_settled": 4200,
    "line_items": [
      {"description": "Annual plan", "amount": 4200}
    ]
  }
}
```

An unknown identifier returns `PAY_4001`.

### Errors
`PAY_4001`, `RATE_LIMITED`

### Example
```bash
curl https://api.example.com/v3/payments/pay_3Kd91xR2?expand=receipt \
  -H "Authorization: Bearer sk_test_REDACTED"
```
