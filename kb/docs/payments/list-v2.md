---
doc_id: payments-list-v2
route: /v2/payments
version: v2
area: payments
status: current
replaced_by: null
description: How to list payments in v2 with offset pagination and read the total count
url: https://docs.example.com/v2/payments/list
---

## GET /v2/payments

Lists payments for the account, newest first. v2 uses offset pagination. Pass `offset` and `limit` as query parameters on `/v2/payments` and read `total_count` from the response to know how many payments match the filter. The maximum `limit` is 100, and a larger value is rejected.

### Request
| Field | Type | Required | Notes |
|---|---|---|---|
| offset | integer | no | Number of payments to skip, defaults to 0 |
| limit | integer | no | Page size, defaults to 20, maximum 100 |
| state | string | no | Filter by state such as authorized or captured |
| created_after | string | no | Timestamp filter |

### Response
Returns an array of payment objects plus the offset, the limit, and `total_count`.

```json
{
  "data": [
    {
      "id": "pay_3Kd91xR2",
      "amount": 4500,
      "currency": "usd",
      "state": "captured"
    }
  ],
  "offset": 0,
  "limit": 20,
  "total_count": 412
}
```

Rate limits in v2 allow 30 requests per minute in sandbox and 60 requests per minute in production. Paging quickly through a large result set can exceed that and return `RATE_LIMITED`.

### Errors
`RATE_LIMITED`, `PAY_4001`

### Example
```bash
curl "https://api.example.com/v2/payments?offset=40&limit=20" \
  -H "Authorization: Bearer sk_test_REDACTED"
```
