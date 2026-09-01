---
name: "agora-execute"
description: "Execute a permitted transition step for an assigned Agora role"
---

# Execute governed work

In at most two sentences, state the governed outcome and the actor, authority, gate, evidence,
budget, and verification you will check. Continue requested in-scope work; pause for a material
choice, human-only approval, or unapproved external, destructive, or costly action.

Use `AGORA_CONTEXT`. If absent, use compact
`agora work inspect --swarm "$AGORA_SWARM" --work "$AGORA_WORK"`, or
`agora next --actor "$AGORA_ACTOR" --limit 1` when work is unknown. Reuse `snapshot_token`; use
`--full` only for a specific ambiguity. Never orient from `.agora/activity.md`, a full event ledger,
or an earlier `RESULT.md`. On retry, read `SUMMARY.md` and inspect only the narrow diagnostic tail it
identifies. Preserve a selected `AGORA_TRACE`; otherwise use `compact`.

Confirm swarm, actor, assignment, work, state, outgoing edge, role tools, WIP, gates, and remaining
usage. Derive actions from the Method Pack. Batch safe actions until human attention, missing
authority, failure, no progress, or session bounds. A new controller may use
`--until-blocked --max-steps 3`; never launch one recursively. Persist at least one material
transition, artifact, evidence, approval, block, or delegation. Never choose rework to evade a
higher-priority human decision.

For a controller session use the narrowest profile: `efficient` with a 64 KiB transcript for
inspection, evidence, transitions, and retry diagnosis; `balanced` with 128 KiB for ordinary
delivery; `complex` only for substantive implementation or review. Treat the session timeout and
output bounds as immutable. The configured runtime owns the concrete model.

Keep tool output below 200 lines or 32 KiB where supported. Use quiet commands, narrow ranges, and
targeted tests. Store long diffs, reports, and logs in durable artifacts; return only status, failing
cases, and references. Do not print whole files, repository-wide diffs, dependency trees, or
successful build logs.

Use `agora tool invoke` for external operations and read only the selected environment policy.
Read the related `DELEGATION.md` for delegated work. For repository history, follow
`.agora/STANDARDS.md` and the governed `repository/commit` operation. Do not invent transitions,
approvals, usage, or authority. Agora records an authentic Codex token footer automatically; add
other authoritative telemetry with `agora usage add`, without duplication.

If work cannot proceed, record an authorized block with its reason. Do not mutate blocked or
cancelled work. Finish with the durable change, checks confirmed, blocker, and next action.

Execution request: `$ARGUMENTS`
