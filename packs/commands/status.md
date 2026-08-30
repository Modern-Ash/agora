---
name: "agora-status"
description: "Inspect and validate durable Agora project state"
---

# Inspect Agora state

When invoked from chat or another non-TTY host, set `AGORA_TRACE=compact` and relay Agora's stderr
lines; keep stdout intact for the structured result.

Use `agora status`, `agora next`, `agora inbox`, and the domain `list` commands before selecting work
or reporting project state.
Use `agora event list` for attributed history and `agora validate` before relying on cross-record
references. Treat validation errors as durable-state problems: report the exact code and path, and do
not silently rewrite or infer missing records. Distinguish Method Pack state from work
`operational-status`. Inspect nested status changes before explaining a block, resumption, rejection,
or cancellation.

Query target: `$ARGUMENTS`
