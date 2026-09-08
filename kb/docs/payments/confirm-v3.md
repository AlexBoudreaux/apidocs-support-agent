---
doc_id: payments-confirm-v3
route: /v3/payments/{id}/confirm
version: v3
area: payments
status: current
replaced_by: null
description: How to complete 3DS authentication on a payment in v3 with confirm, which does not move money.
url: https://docs.example.com/v3/payments/confirm
---

## POST /v3/payments/{id}/confirm

Completes the 3DS authentication step for a payment. Confirm is new in v3 and moves no money. It is not the step that takes funds, which is `capture` at `/v3/payments/{id}/capture`. Call `/v3/payments/{id}/confirm` when a create or capture attempt returned `PAY_4030`, then capture the payment once authentication succeeds.

### Request
| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | path | yes | Payment identifier that requires authentication. |
| `return_url` | string | yes | Where the cardholder is sent after the challenge completes. |
| `authentication_data` | object | no | Values collected from the challenge flow. |

### Response
Returns the payment with its authentication state. When a challenge is needed, `next_action` carries the redirect target.

```json
{
  "id": "pay_3Kd91xR2",
  "status": "requires_capture",
  "authentication_status": "succeeded",
  "next_action": null,
  "confirmed_at": "2026-01-08T17:08:40Z"
}
```

A successful confirmation emits the `payment.confirmed` webhook event. Confirming a payment that is already captured or otherwise past this step returns `PAY_4022`.

### Errors
`PAY_4030`, `PAY_4022`, `PAY_4001`, `RATE_LIMITED`

### Example
```bash
curl -X POST https://api.example.com/v3/payments/pay_3Kd91xR2/confirm \
  -H "Authorization: Bearer sk_test_REDACTED" \
  -H "Content-Type: application/json" \
  -d '{"return_url":"https://merchant.example.com/checkout/complete"}'
```
