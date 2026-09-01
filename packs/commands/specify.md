---
name: "agora-specify"
description: "Specify governed work and its artifact and evidence requirements"
---

# Specify work

In at most two sentences, tell the user what you will specify and which ambiguity, authority, gate,
artifact, and evidence checks you will confirm. Continue without reconfirming requested in-scope
work; pause only when a material decision belongs to the user or an authorized role.

Prefer `AGORA_CONTEXT`. For existing work, start with
`agora work inspect --swarm <swarm> --work <work>`; on an older CLI, fall back to targeted
`show` and `readiness` queries. Read only remaining relevant policy and repository context. Create
unambiguous criteria and required artifact kinds; keep what and why separate from implementation
until planning is permitted.

Before treating the work as unambiguous, inspect its current Method Pack state, outgoing
transitions, gates, assigned roles, and `PROTOCOL.md`. If the next gate declares
`require-resolved-clarifications`, always invoke
`agora work clarify --swarm <swarm> --work <work> --by <actor>` using an actor whose assigned role
permits `work.clarify`; otherwise invoke it whenever material uncertainty remains. Agora compiles
the clarification context from the active Method Pack, so do not assume Scrum ceremonies, Kanban
flow policies, Spec-driven phases, or custom-method semantics that the pack does not declare.

Relay material questions once, together with clearly labelled proposed answers. Stop only before
dependent decisions. A runtime suggestion never satisfies a criterion, approval, evidence, or
transition. After authorized resolution, register the specification. Rerun clarification only when
unresolved or stale, then run traceability once before transition.

Preserve a selected `AGORA_TRACE`; otherwise use `compact`. Report only material phases or blockers,
then the recorded specification, confirmed checks, unresolved decisions, and next action.

Requested work: `$ARGUMENTS`
