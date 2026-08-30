---
name: "agora-specify"
description: "Specify governed work and its artifact and evidence requirements"
---

# Specify work

Read the active swarm, Method Pack, constitution, tool policy, and existing repository context.
Create a work item with unambiguous acceptance criteria and required artifact kinds. Keep the what
and why separate from implementation choices until the workflow permits planning.

Before treating the work as unambiguous, inspect its current Method Pack state, outgoing
transitions, gates, assigned roles, and `PROTOCOL.md`. If material uncertainty remains, invoke
`agora work clarify --swarm <swarm> --work <work> --by <actor>` using an actor whose assigned role
permits `work.clarify`. Agora compiles the clarification context from the active Method Pack, so do
not assume Scrum ceremonies, Kanban flow policies, Spec-driven phases, or custom-method semantics
that the pack does not declare.

Relay the resulting questions and proposed answers to the user. Clearly identify unanswered
questions and stop before any decision that depends on them. Clarification is advisory: never mark
criteria satisfied, grant approval, register evidence, or transition work merely because a runtime
suggested an answer. After the user or an authorized role resolves the ambiguity, persist the
decision through the Method Pack's ordinary governed commands and rerun `agora work traceability`
to detect stale clarification provenance.

When invoked from chat or another non-TTY host, preserve a caller-selected `AGORA_TRACE`; otherwise
set `AGORA_TRACE=compact` and relay Agora's stderr phases separately from structured stdout.

Requested work: `$ARGUMENTS`
