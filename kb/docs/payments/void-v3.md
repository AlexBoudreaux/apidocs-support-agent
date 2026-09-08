---
doc_id: payments-void-v3
route: /v3/payments/{id}/void
version: v3
area: payments
status: deprecated
replaced_by: /v3/payments/{id}/reversal
description: The void route is removed in v3 and reversal replaces it for releasing an uncaptured authorization.
url: https://docs.example.com/v3/payments/void
---

## POST /v3/payments/{id}/void

The void route is removed in v3. `/v3/payments/{id}/void` is no longer served and returns 404 for every request. Use `/v3/payments/{id}/reversal` instead, which does the same thing under a clearer name. It releases an authorization that has not been captured and frees the held funds on the cardholder account. The old call maps onto the new one directly. The payment identifier stays in the same path position, the method is still POST, and the optional `amount` field carries over unchanged for a partial release, defaulting to the full authorized amount. The `reason` field carries over as well. The response shape is the same in spirit, with the reversal identifier returned as `id` and the payment identifier returned as `payment_id`. Reversal emits the `payment.reversed` webhook event, which is the event the old void call emitted. One difference matters. Reversal only applies to a payment that has not been captured. If the payment was already captured, the reversal call returns `PAY_4023` and you should call `/v3/payments/{id}/refund` instead to return the settled money. Reverse one payment per request.

### Errors
`PAY_4023`, `PAY_4022`, `PAY_4001`, `RATE_LIMITED`
