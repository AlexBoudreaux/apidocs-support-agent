---
doc_id: webhooks-ping-v3
route: /v3/webhooks/ping
version: v3
area: webhooks
status: deprecated
replaced_by: /v3/webhooks/endpoints/{id}/test
description: the removed v3 webhooks ping route and how to reach the same result with the per-endpoint test route
url: https://docs.example.com/v3/webhooks/ping
---

## POST /v3/webhooks/ping

The ping route is removed in v3 and returns 404 for every account. In earlier versions a single call to `/v3/webhooks/ping` had no target parameter and fired a synthetic event at every registered endpoint at once, which made it impossible to tell which receiver was broken without reading the delivery rows afterwards. Use `POST /v3/webhooks/endpoints/{id}/test` instead. The old call maps onto the new one by fanning it out yourself. List the endpoints with `GET /v3/webhooks/endpoints`, then call the test route once per endpoint id, passing that id as the `{id}` path parameter. Each call sends one synthetic event to one endpoint and returns the delivery row for that attempt, so a failing receiver is identified by the call that failed rather than by a later search. The test route also accepts an optional `event_type` field, which ping never had, so you can exercise a specific type name against a single receiver. Signatures on the synthetic event are computed with the per-endpoint secret returned once when that endpoint was created, so verify each test payload against the key you stored for that endpoint.

### Errors
`WHK_4004`, `RATE_LIMITED`
