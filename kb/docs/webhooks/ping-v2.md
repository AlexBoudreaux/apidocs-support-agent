---
doc_id: webhooks-ping-v2
route: /v2/webhooks/ping
version: v2
area: webhooks
status: current
replaced_by: null
description: How to send a synthetic ping event to every registered webhook endpoint on the account in v2.
url: https://docs.example.com/v2/webhooks/ping
---

## POST /v2/webhooks/ping

Sends a synthetic ping event to every registered endpoint on the account. Use `POST /v2/webhooks/ping` after a network change or a handler deploy to confirm that all of your destinations still accept traffic. The ping does not represent anything that happened to a payment, so it is safe to fire at any time.

The endpoints test route targets a single endpoint instead of all of them. Reach for that one when you are debugging one url. Inactive endpoints are skipped by the ping.

Each ping creates one delivery per active endpoint, sent one delivery at a time, and those deliveries appear in the delivery history alongside real traffic. The payload is signed with the account-level signing secret, shared by every endpoint.

### Request
| Field | Type | Required | Notes |
|---|---|---|---|
| message | string | no | Free text echoed back in the ping payload |

### Response
Returns one entry per endpoint that was pinged.

```json
{
  "pinged": [
    {
      "endpoint_id": "whe_71bQm4",
      "delivery_id": "whd_88fLz2",
      "response_status": 200,
      "succeeded": true
    }
  ],
  "endpoint_count": 1
}
```

An endpoint that does not answer after 5 attempts is marked failed with `WHK_4100`.

### Errors
`WHK_4100`, `WHK_4221`, `RATE_LIMITED`

### Example
```bash
curl -X POST https://api.example.com/v2/webhooks/ping \
  -H "Authorization: Bearer sk_test_REDACTED" \
  -H "Content-Type: application/json" \
  -d '{"message":"deploy check"}'
```
