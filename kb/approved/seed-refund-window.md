---
doc_id: approved-seed-001
source: approved_answer
route: /v3/payments/{id}/refund
version: v3
area: payments
status: current
replaced_by: null
description: Refund returns PAY_4013 on a payment from four months ago but the same call works on a recent one
url: https://docs.example.com/v3/payments/refund
---

## Approved answer

Ticket SNOW-10041, approved by the developer support team on 2026-08-27. Reviewed against `payments-refund-v3` and `payments-errors#PAY_4013`.

The `PAY_4013` you are seeing is the refund window, not a permissions or amount problem. On v3 a captured payment can be refunded for up to 90 days after the capture settles. The payment in your example settled about four months ago, so it is outside that window and the API rejects the refund. The recent payment is inside the window, which is why the identical call succeeds there.

Two things worth checking before you write this off.

First, confirm which version you are calling. The window is shorter on v2, where it is 30 days after capture. If part of your traffic still goes to `POST /v2/payments/{id}/refund`, payments you expect to be refundable at day 60 will fail there and succeed on `POST /v3/payments/{id}/refund`.

Second, make sure you are not looking at a payment that was authorized but never captured. That case returns `PAY_4022` rather than `PAY_4013`, and the right call is `POST /v3/payments/{id}/reversal`, which releases the authorization instead of returning settled funds.

For payments past 90 days there is no API path to reverse the charge. Those have to be handled outside the payments API by your operations team.

Reference: https://docs.example.com/v3/payments/refund
