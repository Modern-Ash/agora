# Domain model

## Method Pack

A Method Pack is the unit of lifecycle customization. It defines required roles, allowed actor kinds
and actions, ordered work states, terminal state, protocol, tool policy, artifacts, evidence, and
gates. Its identifier is open: Scrum and Kanban are installed, editable presets, while any custom
pack may implement the same Markdown contract.

No Method Pack is privileged by the core. A project can model a standard methodology, an internal
software delivery process, an operational runbook, or a purpose-built hybrid lifecycle.

## Actor, role, and assignment

An **Actor** has an identity, kind, and capabilities. Kinds include human, AI agent, swarm, service,
and automation. A **Role** declares required capabilities, allowed actor kinds, and allowed actions.
An **Assignment** temporarily links an actor to a role within a swarm.

Identity does not change when work moves from a person to an AI agent or swarm. The assignment changes
and the handoff is preserved. A swarm can act as a composite actor inside another swarm.

## Swarm

A swarm is a temporary team associated with an objective, Method Pack, and branch. It starts as
`forming`, becomes `ready` when every required role is assigned, becomes `running` when work advances,
and becomes `completed` when every work item reaches the terminal state.

## Work

A work item is a Markdown directory containing description, state, criteria, artifacts, and evidence.
Its workflow comes from `METHOD.md`; it is not hard-coded into an LLM integration.

Work content and artifact references are opaque to the core. Agora can govern a Python service, a
Java application, infrastructure definitions, documentation, or a polyglot system without changing
the lifecycle engine.

To act, an actor must:

1. Be registered in the user or project scope.
2. Be assigned to a swarm role.
3. Have a kind and capabilities accepted by that role.
4. Have the action listed in the role's `allowed-actions`.

## Artifact and evidence

An artifact is a durable output or external reference, such as code, a specification, ticket, build,
review, approval, or deployment. Evidence records a verifiable result and its producer. The terminal
gate requires satisfied criteria, required artifact kinds, and successful evidence.

## Tool

A tool represents a capability in the developer's daily ecosystem: repository, Jira, CI/CD,
Confluence, cloud, observability, or communication. Method Pack, project, role, and actor restrict its
use. Authentication and secrets remain outside versioned documents.

## Environment

IDE, CLI, runner, and cloud agent are execution environments. They do not own Agora state. Every
environment reads and writes the same workspace protocol and synchronizes through Git.

## Model configuration

Provider and model identify the selected execution environment. They are strings in configuration,
not a closed list or a core SDK dependency. Changing an LLM must not change actor identity, workflow
state, artifacts, or governance history.
