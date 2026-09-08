# Friction Log

Deliverable for the LangChain take-home. Rough edges hit with LangChain, LangGraph, and LangSmith while building an API documentation support pipeline over a week. Three entries. Each one changed the build.

Format per entry:

```
## YYYY-MM-DD | <phase or session name> | <library>
**What I was trying to do:**
**What happened:**
**Workaround or resolution:**
**Severity:** blocker | annoying | cosmetic
```

---

## 2026-09-07 | Whole build | LangSmith SDK and docs

**What I was trying to do:** Set up the entire online loop from code. I work inside a coding agent and I want it to be able to do everything, not most things. The loop needs an annotation queue, a rule that routes heavy-edit traces into it, an online evaluator on the tracing project, and a dashboard chart of the edit score over time.

**What happened:** Half of it has SDK methods, half of it doesn't. Annotation queues and adding examples from traces are clean in the Python SDK and the docs link you to the code. Rules, online evaluator wiring, and charts exist only as REST endpoints, `POST /api/v1/runs/rules`, `/platform/evaluators`, `/charts/create`. The how-to pages for those three features are UI screenshots and never mention that an API exists. I only found the endpoints by reading the OpenAPI spec. So the build spec ended up with a section literally called "Alex, LangSmith clicks," and the agent couldn't finish the job.

**Workaround or resolution:** Did those three in the browser. If I did it again I'd hit the REST endpoints with a plain HTTP client, but the docs should say that's possible on the feature page, and the SDK should cover it. Data operations have SDK support, workspace configuration doesn't, and the feature pages don't admit it. Details and URLs in `docs/research/langsmith-api-coverage.md`.

**Severity:** annoying

---

## 2026-09-07 | Verification pass | LangSmith SDK

**What I was trying to do:** Write three feedback scores onto a trace after a human approves a ticket, using `client.create_feedback()`. This is the label the whole online loop runs on.

**What happened:** The SDK warned that I should also pass which project the run belongs to. I passed `project_id=`, which is what every other call uses. `create_feedback` raises on that, `project_id cannot be provided if run_id or trace_id is provided`. The argument it actually wants is `session_id`. My own catch-all swallowed the error, the next log line said the write succeeded, and for several days every approved ticket wrote zero feedback. Found it by reading feedback back from LangSmith and getting nothing.

**Workaround or resolution:** Passed `session_id=`, made the failure log at error level, added a test with a fake client that reproduces the SDK's own validation. Half of this is on me for swallowing the exception. The half on the SDK is a warning that points you at a parameter name the same function then rejects.

**Severity:** blocker

---

## 2026-09-04 | Build, review and post_send | LangGraph and LangSmith

**What I was trying to do:** Put the human's edit score on the trace that drafted the answer, so I can open a bad draft's trace and see its score next to it.

**What happened:** A ticket runs in two halves. The pipeline runs and stops at `interrupt()`, then the person approves and the graph resumes with `Command(resume=...)`. In LangGraph that's one thread. In LangSmith it's two traces, because the resume is a second `invoke()`. The feedback gets written at the end, so it landed on the short approval trace, not on the one that did the retrieval and drafting. Nothing in the interrupt docs says the trace is about to split. Took a while to work out why the draft traces had no scores.

**Workaround or resolution:** The first node grabs `get_current_run_tree().trace_id` and stores it in state. Post send writes the same feedback to both traces. Small fix, but it's something you have to know, and I'd want the HITL docs to say it.

**Severity:** annoying
