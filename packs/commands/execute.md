---
name: "agora-execute"
description: "Execute a permitted transition step for an assigned Agora role"
---

# Execute governed work

In at most two sentences, tell the user the governed outcome and actor, authority, gate, evidence,
budget, and verification checks. Continue without reconfirming requested in-scope work; pause for a
material choice, human-only approval, or unapproved external, destructive, or costly action.

Preserve a selected `AGORA_TRACE`; otherwise use `compact`. Report only material phases, blockers,
or long-running progress; omit raw traces and payloads unless debugging was requested.

Use `AGORA_CONTEXT`; if absent, start with `agora next --actor "$AGORA_ACTOR" --limit 1` and expand
only as needed. Derive actions from durable Method Pack state. Batch safe actions until human
attention, missing authority, failure, no progress, or session bounds. For a new controller run,
prefer `--until-blocked --max-steps 3`; never launch it recursively. Record at least one governed
transition, artifact, evidence, approval, block, or delegation. Never choose rework to avoid a
higher-priority human decision.
Treat the timeout and output limits in `AGORA_SESSION` as immutable execution policy. The controller
records bounded process output in the session `RESULT.md`; place material outcomes in governed work
artifacts and evidence rather than relying on that process log.

Confirm swarm, actor, assignment, work, state, and outgoing edge. Respect role tools, WIP, and gates.
Persist material decisions, artifacts, evidence, approvals, and interactions. Invoke external
operations through `agora tool invoke`. For an environment, select `.agora/environments` policy and
confirm role, approval, and evidence requirements.
When a runtime or reviewed adapter reports measured resource consumption, append it with
`agora usage add` and cite the authoritative telemetry reference. Never estimate or invent usage.
Check `agora usage status --swarm <swarm> --work <work>` before allocating or launching bounded
work so the next operation fits the durable remaining budget.
When work is delegated, read the related `DELEGATION.md` and act only within its parent or child
contract. Do not invent a transition or bypass a gate.

When repository history is required, read `.agora/STANDARDS.md` and use the governed
`repository/commit` operation with a Conventional Commits 1.0.0 message. Do not bypass its input
validation with an ungoverned Git command.

If active work cannot proceed, use an authorized block with an explicit reason instead of inventing
a Method Pack state. Do not mutate blocked or cancelled work. Resume only after its stated blocker is
resolved. Treat delegation rejection as child authority and delegation cancellation as parent
authority; neither operation permits silently rewriting independently owned child work.

Finish with the durable change, checks actually confirmed, verification, blocker, and next action.

Execution request: `$ARGUMENTS`
