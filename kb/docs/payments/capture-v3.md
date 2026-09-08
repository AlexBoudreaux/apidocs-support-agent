---
doc_id: payments-capture-v3
route: /v3/payments/{id}/capture
version: v3
area: payments
status: current
replaced_by: null
description: How to capture an authorized payment in v3 and why capture is not the 3DS authentication step handled by confirm.
url: https://docs.example.com/v3/payments/capture
---

## POST /v3/payments/{id}/capture

Captures an authorization and moves money for a payment that has already been authenticated. Capture is not the 3DS authentication step. That step is `confirm`, at `/v3/payments/{id}/confirm`. A payment that still needs authentication returns `PAY_4030` from `/v3/payments/{id}/capture` and must be confirmed first, then captured.

### Request
| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | path | yes | Payment identifier of an authorized payment. |
| `amount_to_capture` | integer | no | Smallest currency unit. Defaults to the full authorized amount. |
| `statement_descriptor` | string | no | Text shown on the cardholder statement. |

Capture one payment per request. Capturing a payment that is already captured or was reversed returns `PAY_4022`.

### Response
Returns the updated payment with the captured amount and the settlement timestamp.

```json
{
  "id": "pay_3Kd91xR2",
  "amount": 4200,
  "amount_captured": 4200,
  "currency": "usd",
  "status": "captured",
  "captured_at": "2026-01-08T17:09:52Z"
}
```

A successful capture emits the `payment.captured` webhook event once the capture settles.

### Errors
`PAY_4030`, `PAY_4022`, `PAY_4001`, `RATE_LIMITED`

### Example
```bash
curl -X POST https://api.example.com/v3/payments/pay_3Kd91xR2/capture \
  -H "Authorization: Bearer sk_test_REDACTED" \
  -H "Content-Type: application/json" \
  -d '{"amount_to_capture":4200}'
```
