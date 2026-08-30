---
schema: "agora/protocol/v1"
project: "{{PROJECT_NAME}}"
---

# Collaboration protocol

1. Read `.agora/project.md`, this protocol, the constitution, and the active Method Pack.
2. Identify the active swarm, assigned role, current work state, and allowed tools.
3. Do not act outside the capabilities and permissions of the assignment.
4. Record material interactions and decisions in the active swarm. Use `.agora/activity.md` and
   `agora activity list` as the linked project chronology; do not edit generated ledger entries.
5. Register produced artifacts and evidence before requesting completion.
6. Use a handoff when responsibility moves between a human, AI agent, service, or swarm.
   An AI executor may assist a human role holder without changing the assignment; assistance never
   grants ownership or human approval authority.
7. Use a delegation record when linked child work is proposed, accepted, or collected.
8. Stop and request approval when a policy or gate cannot be satisfied.
9. Use installed Tool Pack operations for governed external actions, retain their results, and use
   `agora tool result --run <id>` when captured provider output must be inspected.
10. In chat and non-TTY environments, run Agora with `AGORA_TRACE=compact` and relay its stderr
   milestones. Never merge trace lines into the structured stdout result.
11. Read `.agora/STANDARDS.md` and validate commit messages before creating repository history.
12. When an actor requires authentication, prepare, externally sign, and apply each covered
    lifecycle mutation through its durable `ACTION.md` intent.
13. For environment-aware Tool Runs, select a project environment and satisfy its role, approval,
    and evidence policy before preparation and again before launch.
14. When `.agora/coordination.md` selects an external lease, do not bypass the Agora mutation path;
    local and distributed writer coordination are cumulative.
15. During a running session, record concise material milestones through `agora session progress`.
    Do not persist chain-of-thought, hidden reasoning, credentials, or raw provider output there.
16. Treat clarifications, checklists, consistency reports, and generated Gherkin as advisory until
    the active Method Pack's existing criteria, evidence, artifact, approval, and transition rules
    make an exact durable record binding. Runtime fallback changes execution backend only; it never
    changes actor identity or authority.
17. Before relying on generated advisory output, inspect `agora work traceability` or validation
    warnings and regenerate records whose bound input SHA-256 no longer matches current work.

The repository and its active branch are the shared source of truth. Chat history is not durable
project state unless its relevant outcome is recorded in Agora files. `RESULT.md` retains bounded
runtime output, while `SUMMARY.md` and the Activity Ledger provide the reviewable execution trail.
