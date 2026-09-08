---
doc_id: payments-receipt-v3
route: /v3/payments/{id}/receipt
version: v3
area: payments
status: deprecated
replaced_by: /v3/payments/{id}?expand=receipt
description: The receipt route is removed in v3 and the expand receipt query parameter on the payment get route replaces it.
url: https://docs.example.com/v3/payments/receipt
---

## GET /v3/payments/{id}/receipt

The receipt route is removed in v3. `/v3/payments/{id}/receipt` is no longer served and returns 404 for every request. Fetch the receipt through the payment itself instead, using `/v3/payments/{id}?expand=receipt`. That query parameter inlines the full receipt object in the payment response, so one call now returns both the payment and its receipt where v2 needed two. The old call maps onto the new one cleanly. The payment identifier stays in the same path position and the method is still GET. Everything the old response returned at the top level now sits under the `receipt` key, with the same field names, including `receipt_number`, `issued_at`, `amount_settled`, and `line_items`. Read those fields one level deeper and nothing else changes. Omitting `expand` returns the payment without the receipt, which is the cheaper call when you only need the payment state. A receipt exists only after the payment has settled, so a payment that has not been captured returns a null `receipt`. An unknown payment identifier returns `PAY_4001`.

### Errors
`PAY_4001`, `RATE_LIMITED`
