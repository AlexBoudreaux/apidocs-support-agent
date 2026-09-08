# LangSmith feature coverage from code

Checked on 2026-09-07 against the live OpenAPI spec at `https://api.smith.langchain.com/openapi.json`, the docs at docs.langchain.com/langsmith, and the installed Python SDK `langsmith` 0.12.1 (source at `.venv/lib/python3.12/site-packages/langsmith/client.py`).

| # | Feature | Verdict | SDK method | REST endpoint | Docs lead you there? |
|---|---------|---------|-----------|---------------|----------------------|
| 1 | Annotation queues, create and add a run | SDK | `client.create_annotation_queue`, `client.add_runs_to_annotation_queue`, `client.annotation_queues.items.create` | `POST /api/v1/annotation-queues`, `POST /api/v1/annotation-queues/{queue_id}/runs`, `POST /api/v1/platform/annotation-queues/{queue_id}/items` | Yes |
| 2 | Automation rule on a tracing project | REST only | none | `POST /api/v1/runs/rules` | No |
| 3 | Online LLM-as-judge evaluator on live traces | REST only | partial, see note | `POST /api/v1/platform/evaluators` plus `POST /api/v1/runs/rules` | No |
| 4 | Dashboards and custom charts | REST only | none | `POST /api/v1/charts/create` and `POST /api/v1/charts/section` | No |
| 5 | Add an example to a dataset from a trace | SDK | `client.create_example_from_run`, or `client.list_runs` plus `client.create_examples` | `POST /api/v1/examples`, `POST /api/v1/examples/bulk` | Yes |

## Notes

### 1. Annotation queues

Fully supported in the Python SDK. `create_annotation_queue` is at line 9178 and `add_runs_to_annotation_queue` at line 9298 of `/Users/alexboudreaux/Developer/temp-langgrapgh-agent/.venv/lib/python3.12/site-packages/langsmith/client.py`. There is also a newer typed resource, `client.annotation_queues.items.create`, backed by the generated OpenAPI client in `langsmith/_openapi_client/resources/annotation_queues/`. That newer one takes both run items and thread items in one call.

The docs do lead you there. The feature how-to page at https://docs.langchain.com/langsmith/annotation-queues is UI instructions, but it links out to https://docs.langchain.com/langsmith/annotation-queues-sdk which shows the Python and TypeScript code. So you do not have to dig.

### 2. Automation rules

There is no SDK method. Nothing in `client.py` creates a rule, and the generated OpenAPI client does not expose a rules resource either. The REST endpoint does exist and is marked public in the spec, `POST /api/v1/runs/rules`, documented at https://docs.langchain.com/langsmith/smith-api/run/create-rule.

The request body is `RunRulesCreateSchema` and it has everything you need for the feedback example, including `session_id` for the tracing project, `filter` for the trace or run condition, `sampling_rate`, and `add_to_annotation_queue_id` for the action. So a rule that watches for `edit_tier == 2` feedback and pushes the run into a queue is expressible over REST.

The docs do not lead you there. The how-to page at https://docs.langchain.com/langsmith/rules is entirely UI steps. It mentions the API field name `sampling_rate` in passing but never says you can create the rule over the API and never links to the endpoint. You only find it by reading the OpenAPI spec or browsing the API reference section.

### 3. Online evaluators

Half supported. The evaluator definition itself has an SDK path. `client.evaluators` is a property on the client, at line 1646 of `client.py`, and it returns the generated `OnlineEvaluatorsResource`, which has `create`, `retrieve`, `update`, `list`, `delete`, `bulk_delete`, and `spend`. That maps to `POST /api/v1/platform/evaluators`, documented at https://docs.langchain.com/langsmith/smith-api/evaluators/create-evaluator.

But creating the evaluator is not the whole job. Attaching it to a tracing project with a sampling rate happens through a run rule. The `OnlineEvaluator` type in the SDK carries a `run_rules` list, see `langsmith/_openapi_client/types/online_evaluator.py` and `online_evaluator_run_rule.py`, and there is no SDK method to create those rules. So the full configuration still needs `POST /api/v1/runs/rules`, which is REST only. That is why the verdict is REST only rather than SDK.

One more caveat. `client.evaluators` calls `_check_backend_version(min_version="0.16.0")`, so self hosted installs older than that will reject it.

The docs do not lead you there. https://docs.langchain.com/langsmith/online-evaluations is pure UI walkthrough with no code and no link to the evaluator endpoints.

### 4. Dashboards and charts

No SDK method at all. Grepping the whole installed package for chart or dashboard turns up nothing outside of unrelated matches. The REST surface is real though. `POST /api/v1/charts/create` creates a chart, https://docs.langchain.com/langsmith/smith-api/charts/create-chart, and `POST /api/v1/charts/section` creates a section, which is what the UI calls a dashboard, https://docs.langchain.com/langsmith/smith-api/charts/create-section.

A chart of a feedback key over time is expressible. The spec has `CustomChartFeedbackScoreMetricScalar` and `CustomChartFeedbackCountMetric` metric types, plus `CustomChartFilterByTracingProject` and group by options. So the shape you want is supported by the payload.

Note that `POST /api/v1/charts` is confusingly a read, its summary is "Read Charts". The create is the `/charts/create` path.

The docs do not lead you there. https://docs.langchain.com/langsmith/dashboards is UI only, with no mention that the chart API exists.

### 5. Add an example to a dataset from a trace

Supported in the SDK two ways. `client.create_example_from_run(run, dataset_id=...)` at line 6360 of `client.py` takes a `Run` object directly. The more common path in the docs is to pull runs with `client.list_runs` and then bulk load with `client.create_examples`.

The docs mostly lead you there. https://docs.langchain.com/langsmith/manage-datasets-programmatically has a "Create a dataset from traces" section with Python, TypeScript, and Java code. It uses `list_runs` plus `create_examples` and does not mention `create_example_from_run`, which you only find in the SDK source or the reference. The UI page at https://docs.langchain.com/langsmith/manage-datasets covers the multi select and "Add to Dataset" button and does not link to the programmatic page from that section.

## Cross cutting observation

The pattern is consistent. Anything that reads or writes trace and dataset data has first class SDK support. Anything that configures the workspace, meaning rules, evaluator wiring, charts, and dashboards, exists only as REST endpoints and the feature how-to pages never admit that. If you want these in code you have to hit `api.smith.langchain.com` with a plain HTTP client and your `x-api-key` header.
