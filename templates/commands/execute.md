---
name: "agora-execute"
description: "Execute a permitted transition step for an assigned Agora role"
---

# Execute governed work

Use `agora next --actor "$AGORA_ACTOR"` to derive the current action from durable Method Pack state.
When launched through `agora run`, read the context at `AGORA_CONTEXT` before changing the project.
Record at least one governed transition, artifact, evidence, approval, block, or delegation outcome
before exiting successfully; a bounded `--until-blocked` controller stops when no durable progress is
detected. Never select a rework edge merely to avoid a higher-priority human decision.
Treat the timeout and output limits in `AGORA_SESSION` as immutable execution policy. The controller
records bounded process output in the session `RESULT.md`; place material outcomes in governed work
artifacts and evidence rather than relying on that process log.

Identify the active swarm, actor, assignment, work item, and current Method Pack state. Inspect the
outgoing transition edges and perform only the selected edge using tools allowed to that role.
Respect WIP limits and gates. Persist material decisions, interactions, artifacts, evidence, and
approvals. Invoke installed external operations through `agora tool invoke` so their attribution and
results are durable. When an operation requires an environment, select a policy from
`.agora/environments`, confirm the assigned role permits it, and satisfy its approvals and evidence.
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

Execution request: `$ARGUMENTS`
