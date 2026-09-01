---
name: "agora-status"
description: "Inspect and validate durable Agora project state"
---

# Inspect Agora state

Tell the user in one sentence what state and durable source you will inspect. This is read-only; do
not ask for confirmation.

Use the narrowest query. For named work, start with
`agora work inspect --swarm <swarm> --work <work>`; on an older CLI, use targeted `show` and
`readiness` queries. For work selection use `agora next --actor <actor> --swarm <swarm> --limit 1`.
Use `status` for a project overview, `inbox` for human attention, domain lists to resolve scope,
`event list` for history, and `validate` only for health or cross-record integrity. Do not run all of
them by default.

Preserve a selected `AGORA_TRACE`; otherwise use `compact`. Summarize instead of echoing traces or
payloads. Report validation errors by exact code and path without rewriting or inferring records.
Distinguish Method Pack state from `operational-status`; inspect nested changes only to explain an
interruption. Report state, blockers, next action, and durable source.

Query target: `$ARGUMENTS`
