# Method Pack reference

A Method Pack is a versioned Markdown contract for a work lifecycle. The Agora core does not reserve
method identifiers: `scrum` and `kanban` are bundled examples, while user and project scopes may
install any valid pack.

## Directory contract

```text
my-method/
  METHOD.md             Required lifecycle manifest
  PROTOCOL.md           Recommended collaboration rules
  TOOLS.md              Recommended tool policy
  roles/
    owner.md             One file per required role
    maker.md
  transitions/
    01-proposed-to-active.md
    02-active-to-review.md
  gates/
    completion.md
```

`METHOD.md` and its listed role files are required. Explicit transition files are recommended. A
pack without them remains compatible with the original sequential lifecycle behavior. Gate files,
`PROTOCOL.md`, and `TOOLS.md` are optional, but make policy explicit to both the kernel and its
participants.

## Method manifest

`METHOD.md` starts with JSON-compatible YAML front matter:

```markdown
---
schema: "agora/method/v1"
id: "release-flow"
name: "Release Flow"
version: "1.0.0"
dependencies: [{"kind":"tool","id":"repository","version":">=1.0.0,<2.0.0"}]
required-roles: ["owner", "maker", "validator"]
work-states: ["proposed", "active", "review", "released"]
terminal-state: "released"
wip-limits: {"active": 2, "review": 1}
---

# Release Flow

Describe the lifecycle, its intent, and its completion expectations here.
```

| Attribute | Contract |
| --- | --- |
| `schema` | Must be `agora/method/v1` |
| `id` | Lowercase slug matching `[a-z][a-z0-9-]*` |
| `name` | Non-empty human-readable name |
| `version` | Numeric `MAJOR.MINOR.PATCH`; omitted legacy versions resolve as `0.0.0` |
| `dependencies` | Optional array of version-constrained Method or Tool Pack references |
| `required-roles` | Non-empty array of role ids |
| `work-states` | Non-empty array of unique state ids |
| `terminal-state` | Must identify one of the declared states |
| `wip-limits` | Optional map of state ids to positive integer limits |

Every declared state must be reachable from the first state. The terminal state cannot have outgoing
transitions. For a legacy pack without `transitions/`, Agora derives edges between adjacent states;
in that case the terminal state must remain the final item.

Catalog installation resolves dependencies before copying the pack. Direct source installation
requires them to exist already. See [Pack dependencies](../guides/pack-dependencies.md) for range,
scope, cycle, and replacement rules.

## Transition graph

Each transition is a Markdown contract under `transitions/`:

```markdown
---
schema: "agora/transition/v1"
from: "review"
to: "active"
roles: ["validator"]
---

# Return for changes

Send reviewed work back to active delivery when changes are required.
```

The `roles` array must be non-empty. Add `gate: "completion"` to an edge that must satisfy a named
gate. The actor must be assigned one of the edge's roles, and that role must also grant
`work.transition`. Multiple outgoing
edges and backward edges support branching and rework without bypass flags.

When a transition enters a state with a WIP limit, Agora counts all work in that state for the swarm.
The transition is rejected when the configured limit has already been reached.

## Role manifest

Each required role has a file under `roles/<role-id>.md`:

```markdown
---
schema: "agora/role/v1"
id: "maker"
required-capabilities: ["delivery"]
allowed-actor-kinds: ["human", "ai-agent", "swarm", "automation"]
allowed-actions: ["work.transition", "artifact.add", "evidence.add"]
allowed-tool-capabilities: ["repository.read", "repository.write", "ci.run"]
---

# Maker

Produces the governed outcome and its inspectable artifacts.
```

`required-capabilities` must be present on an actor before assignment. `allowed-actor-kinds` may use
`human`, `ai-agent`, `swarm`, `service`, or `automation`. `allowed-actions` grants authority inside the
swarm; it does not grant operating-system, cloud, or external-service permissions.

`allowed-tool-capabilities` is optional and defaults to no external-tool authority. Each value must
match the capability of an installed Tool Pack operation. See the
[Tool Pack reference](tool-packs.md) for invocation and result contracts.

Actions currently issued by the CLI are:

| Action | CLI operation |
| --- | --- |
| `actor.key.recover` | Authorize another assigned actor's replacement after revocation |
| `actor.key.revoke` | Revoke another assigned actor's active public key |
| `actor.key.rotate` | Authorize the acting actor's next active public key |
| `actor.runtime.update` | Change the acting actor's runtime selection |
| `work.create` | Create a governed work item |
| `work.transition` | Traverse an allowed transition edge |
| `work.block` | Suspend mutations without changing method state |
| `work.resume` | Resume blocked work in its preserved method state |
| `work.cancel` | Close work without claiming method completion |
| `criterion.satisfy` | Mark an acceptance criterion satisfied |
| `artifact.add` | Register a durable output or reference |
| `evidence.add` | Register a successful or failed result |
| `approval.add` | Record approval for a named role |
| `handoff.create` | Transfer the role held by the acting actor |
| `handoff.manage` | Transfer another role under governance authority |
| `work.delegate` | Propose work through the linked child actor holding the role |
| `delegation.manage` | Propose child work on behalf of a governance role |
| `delegation.accept` | Accept a proposal and create work inside the child swarm |
| `delegation.collect` | Register a terminal child result in its parent work |
| `delegation.block` | Suspend a proposal or accepted delegation from the parent |
| `delegation.resume` | Restore a blocked delegation to its prior state |
| `delegation.reject` | Reject a proposal under child authority |
| `delegation.cancel` | Close a delegation under parent authority |

A role may combine actions, but projects should grant only the authority required by that role.
Delegation actions require a linked swarm graph in addition to role authority. See the
[delegated work guide](../guides/delegated-work.md) for the state and attribution rules.
See [interruptions and cancellation](../guides/interruptions-and-cancellation.md) for operational
status rules and recommended authority boundaries.

## Gate manifest

A gate file under `gates/<gate-id>.md` has this form:

```markdown
---
schema: "agora/gate/v1"
id: "completion"
require-all-criteria: true
require-required-artifacts: true
require-successful-evidence: true
required-approval-roles: ["owner"]
---

# Completion gate

Explain what this policy protects and what evidence reviewers should inspect.
```

The three Boolean requirements may be enabled independently. Each role in
`required-approval-roles` must have an approval recorded by an actor currently assigned to that role.
The approving role needs the `approval.add` action. A gate runs only on transition edges that name it.

For backward compatibility, a legacy pack that has no gate files receives a strict `completion` gate
requiring all criteria, required artifacts, and at least one successful evidence record. The derived
transition into its terminal state uses that gate.

Model method-specific rework as explicit transitions with their own allowed roles and gates. Use the
shared operational status only for suspension or cancellation. Agora does not implement a global
gate waiver or transition bypass.

## Protocol and tool policy

`PROTOCOL.md` describes collaboration behavior, handoffs, approvals, and escalation. `TOOLS.md`
describes which external systems and operations are appropriate. LLM adapters read these files as
instructions; the Python kernel does not parse their prose into operating-system, cloud, or
external-service permissions.

Keep secrets out of both files. Refer to a credential or policy managed by the execution environment
instead of embedding its value.

## Install at user scope

```bash
agora method install --source ./release-flow --scope user
agora configure --default-method release-flow
```

The pack is copied to `~/.agora/methods/release-flow`. New projects inherit user packs during
`agora init`.

## Install at project scope

Initialize the project first, then install the pack:

```bash
agora init
agora method install --source ./release-flow --scope project
agora swarm create \
  --id first-release \
  --objective "Deliver the first governed release" \
  --method release-flow
```

The pack is copied to `.agora/methods/release-flow` and belongs to the project repository.

Method Packs may also be discovered from a reviewed local or remotely verified catalog:

```bash
agora pack search --kind method --query release
agora pack install --kind method --id release-flow \
  --registry team-catalog --scope project
```

See [Pack registries](../guides/pack-registries.md) for registry authoring and precedence, and
[Remote registry releases](../guides/remote-registries.md) for versioned distribution and trust.
Catalog-installed copies persist provenance and support explicit preview-first upgrades; see
[Pack updates](../guides/pack-updates.md).

Use `--force` to replace files for a pack with the same id. Review the Git diff because extra files
from the previous version are not automatically deleted.

## Scope and precedence

```text
Agora bundled packs < user packs < project modifications < active swarm selection
```

A user pack with the same id replaces bundled files when a project is initialized. Project files may
then be reviewed and amended locally. A swarm persists the selected method id in `SWARM.md`, so later
changes to the project default do not silently move that swarm to another lifecycle.

## Validation checklist

Before sharing a pack:

1. Install it into an isolated Agora home.
2. Initialize a temporary project with it as the default.
3. Create a swarm and assign every required role.
4. Exercise every forward, branch, and rework transition.
5. Confirm incompatible actor kinds, roles, and missing capabilities are rejected.
6. Fill WIP-limited states and confirm the next entry is rejected.
7. Confirm each gate rejects missing criteria, artifacts, evidence, or approvals as configured.
8. Review the generated Markdown and Git diff.

The [custom lifecycle sample](../../samples/custom-lifecycle/README.md) provides a complete
`release-flow` pack and an executable installation example.
