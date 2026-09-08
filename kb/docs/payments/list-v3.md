---
doc_id: payments-list-v3
route: /v3/payments
version: v3
area: payments
status: current
replaced_by: null
description: How to list payments in v3 with cursor pagination using the cursor and limit query parameters.
url: https://docs.example.com/v3/payments/list
---

## GET /v3/payments

Lists payments for the account, newest first. v3 uses cursor pagination. Pass `cursor` and `limit` as query parameters on `/v3/payments`, then follow `next_cursor` from each response until `has_more` is false. There is no `total_count` field in v3, so do not compute a page count from the response.

### Request
| Field | Type | Required | Notes |
|---|---|---|---|
| `cursor` | query | no | Opaque cursor from `next_cursor`. Omit for the first page. |
| `limit` | query | no | Page size. Default 20. Maximum 100. |
| `status` | query | no | Filter on payment state, for example `captured`. |
| `created_after` | query | no | Timestamp filter in RFC 3339 form. |

Rate limits in v3 are 30 requests per minute in sandbox and 600 requests per minute in production. Paging faster than that returns `RATE_LIMITED`.

### Response
Returns a page of payments plus the cursor fields.

```json
{
  "data": [
    {"id": "pay_3Kd91xR2", "amount": 4200, "currency": "usd", "status": "captured"}
  ],
  "next_cursor": "cur_7Ma20b",
  "has_more": true
}
```

When `has_more` is false, `next_cursor` is null.

### Errors
`RATE_LIMITED`

### Example
```bash
curl "https://api.example.com/v3/payments?limit=100&cursor=cur_7Ma20b" \
  -H "Authorization: Bearer sk_test_REDACTED"
```
