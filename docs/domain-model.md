# Domain model

## Method Pack

A Method Pack is the unit of lifecycle customization. It defines required roles, allowed actor kinds
and actions, work states, explicit transitions, WIP limits, gates, approval requirements, protocol,
and tool policy. Its identifier is open: Scrum and Kanban are installed, editable presets, while any
custom pack may implement the same Markdown contract.

No Method Pack is privileged by the core. A project can model a standard methodology, an internal
software delivery process, an operational runbook, or a purpose-built hybrid lifecycle.

Every Method and Tool Pack has a numeric semantic version and may depend on version ranges of other
packs. A **Pack Dependency** names a `method` or `tool`, its id, and a compatibility constraint.
Catalog resolution selects dependencies before their consumer; project validation treats all
installed packs as one composition and rejects missing, incompatible, or cyclic relationships.

## Actor, role, and assignment

An **Actor** has an identity, kind, and capabilities. Kinds include human, AI agent, swarm, service,
and automation. A **Role** declares required capabilities, allowed actor kinds, and allowed actions.
An **Assignment** temporarily links an actor to a role within a swarm.

Direct assignment bootstraps a forming swarm and can only fill a vacant role. Once a governance
actor is present, `swarm.assign` offers a signed path for remaining vacancies and binds authorizer,
target, role, and current swarm projection. Occupied roles can only change through a handoff, which
preserves both identities and the reason.

An actor may also declare an Ed25519 public identity and require authentication for supported
lifecycle actions, Tool Run launch, and agent-session preparation and launch. Canonical
authorizations bind the actor to one exact prepared operation. The external signer holds the private key; applied records
retain public key, fingerprint, payload digest, and signature so validation can verify the
historical proof independently of the actor's current key.
Each public **Actor Key** has an `active`, `rotated`, or `revoked` lifecycle. Rotation links an old
fingerprint to its replacement. Revocation disables new governed signed operations until an explicit
replacement is installed, without invalidating historical signatures.

Identity does not change when work moves from a person to an AI agent or swarm. The assignment changes
and the handoff is preserved. A swarm can act as a composite actor inside another swarm.

A project-scoped swarm actor may identify a `represented-swarm`. This creates a directed delegation
edge when the actor receives a parent role. The referenced child retains its own domain records and
must be ready or running. Agora rejects delegation cycles and chains beyond the configured maximum
depth. An unlinked swarm actor remains a valid opaque composite team.

A **Handoff** transfers one current role assignment between compatible actors. The outgoing holder
may initiate its own transfer with `handoff.create`; a governance actor may coordinate another role
with `handoff.manage`. The record attributes both actors, the authorizer, reason, optional work, and
time. Prior events and sessions retain their original actor identity.

## Delegation

A **Delegation** binds nonterminal parent work to a proposed child work item through the linked swarm
actor assigned in the parent. It records the child contract, including title, description,
acceptance criteria, required artifacts, and the result artifact kind expected by the parent.

The primary path moves from `proposed` to `accepted` to `collected`. A proposal or accepted contract
may be blocked and resumed to its prior state. The child may reject a proposal; the parent may cancel
a proposed, accepted, or blocked delegation. Acceptance creates child work under the child's own
Method Pack. Collection requires that work to reach its terminal state, then adds an `agora://`
child-work artifact reference and successful delegated-work evidence to the parent. Cancelling an
accepted delegation does not rewrite its independently owned child work. Child artifacts remain
authoritative in the child and parent completion gates remain independent.

A Delegation may carry provider-neutral integer budget limits. Acceptance copies those limits to
the child work. Nested delegations may allocate only inherited dimensions, and non-rejected sibling
allocations cannot exceed the parent work limit. Agora validates declared capacity; consumption
evidence remains the responsibility of the selected runtime or external adapter.

## Swarm

A swarm is a temporary team associated with an objective, Method Pack, and branch. It starts as
`forming`, becomes `ready` when every required role is assigned, becomes `running` when work advances,
and becomes `completed` when every work item reaches the terminal state or is explicitly cancelled,
provided at least one item completed normally. It is `blocked` when every remaining nonterminal item
is blocked and `cancelled` when every item is cancelled.

## Work

A work item is a Markdown directory containing description, state, criteria, artifacts, and evidence.
Its workflow comes from `METHOD.md`; it is not hard-coded into an LLM integration.

Local decomposition creates child work under the same swarm and Method Pack. The child stores a
`parent-work` reference and the parent stores the inverse `child-work-refs` list. Parent completion
or cancellation requires every direct child to be terminal or explicitly cancelled. Cross-swarm
child ownership uses a Delegation instead.

Work also has an orthogonal operational status: `active`, `blocked`, or `cancelled`. Blocking
preserves method state while suspending mutations. Resumption restores activity without traversing a
method edge. Cancellation is terminal for the item but does not claim that its Method Pack gate was
satisfied.

A **Status Change** is a nested, attributed `STATUS.md` record. Its monotonic sequence, action,
source, target, actor, timestamp, and reason preserve interruption history independently of folder
names. The owning `WORK.md` or `DELEGATION.md` remains the current-state projection.

Transition documents connect source and target states and restrict the roles allowed to traverse
each edge. A graph may contain review or verification loops. WIP limits reject entry into a state
whose configured capacity is full.

Work content and artifact references are opaque to the core. Agora can govern a Python service, a
Java application, infrastructure definitions, documentation, or a polyglot system without changing
the lifecycle engine.

To act, an actor must:

1. Be registered in the user or project scope.
2. Be assigned to a swarm role.
3. Have a kind and capabilities accepted by that role.
4. Have the action listed in the role's `allowed-actions`.

## Lifecycle Action

A **Lifecycle Action** is a prepared mutation intent stored independently from current work state.
Its common envelope binds an id, action kind, actor, swarm, work, structured parameters, and a
SHA-256 precondition. Supported kinds cover planned actor key rotations, independently authorized
revocation and recovery, actor runtime updates, work transitions, work interruptions, approvals,
handoffs, work creation, same-swarm decomposition and material records, session preparation, and the
complete delegation lifecycle. Existing-work
mutations cover the work projection, artifacts, evidence, and approvals on which the mutation
depends. Work creation instead covers the swarm projection and binds the complete initial work
definition. Criterion, artifact, and evidence parameters bind their exact durable values.
Interruption reasons are signed and successful actions link exactly to their `STATUS.md`. Approval
parameters bind both the asserted role and durable note. A handoff instead covers the swarm
assignment projection and optional referenced work while binding both actor identities, the role,
and reason.

Signed work decomposition binds the parent work precondition and the complete initial child
contract. Applying it rechecks `work.decompose` authority, parent mutability, and child path
availability. The child links to its parent and the parent retains the inverse child reference.

A signed delegation status decision binds its delegation id and reason to both `DELEGATION.md` and
the parent work digest. Parent governance authorizes block, resume, and cancel; child authority
authorizes reject. The applied action and sequenced delegation `STATUS.md` cross-reference by id.

Signed delegation creation binds the complete child-work contract to the parent work, parent and
child swarm manifests, and linked actor record. Acceptance also binds the current proposal and child
swarm before materializing child work. Collection adds the terminal child work digest before
recording its reference as parent artifact and evidence. Child `WORK.md` keeps its delegation and
parent-work links through every subsequent projection rewrite.

Signed session preparation is a Lifecycle Action whose precondition is the prospective
`CONTEXT.md` digest. The applied action materializes `SESSION.md` and `CONTEXT.md`, and the session
links back to that action. Launch authorization remains separate and signs the materialized context,
resolved runtime, and exact command.

A signed actor runtime update is self-authorized through an assigned swarm role. Its precondition
covers the actor and swarm projections, while apply rechecks current `actor.runtime.update` Method
Pack authority before updating the actor's optional integration, provider, and model overrides.

A signed actor key rotation binds the old and replacement fingerprints, canonical replacement
public key, and reason. Its precondition includes the actor, swarm, and complete public key history.
The old key verifies the action before the replacement becomes active. Revocation and recovery stay
separate because a revoked key cannot provide continuity evidence. A different authenticated actor
must hold explicit Method Pack authority, share the target's swarm, and use a distinct fingerprint.
The signed action binds the target, current key, reason, and recovery key when present.

Applying the action rechecks the precondition, current actor assignment, Method Pack transition,
role authority, WIP limit, gate, and active public key before changing `WORK.md`. Authenticated
actors must provide an external Ed25519 signature. Applied actions retain public verification
evidence; prepared actions whose work changes remain durable but stale and cannot execute.

## Artifact, evidence, and approval

An artifact is a durable output or external reference, such as code, a specification, ticket, build,
review, approval, or deployment. Evidence records a verifiable result and its producer. An approval
is a separate attributed decision made under an assigned role. Gate documents choose whether to
require criteria, artifacts, successful evidence, and approvals from specific roles.

## Tool

A tool represents a capability in the developer's daily ecosystem: repository, Jira, CI/CD,
Confluence, cloud, observability, or communication. Method Pack, project, role, and actor restrict its
use. Authentication and secrets remain outside versioned documents.

A **Tool Pack** declares one executable and a catalog of structured operations. An operation has a
provider-neutral capability, risk classification, arguments, required inputs, optional approval role,
and result kind. A role grants exact values through `allowed-tool-capabilities`; installing a pack
does not grant authority.

Every Tool Pack also resolves a portable execution policy: a direct-process timeout and a combined
captured-output limit. Agora copies that policy into each Tool Run, includes it in signed launch
authorization, and persists bounded results. This policy controls execution duration and audit data
size; it is not filesystem, network, syscall, resource, or process-tree isolation.

A **Tool Adapter** is a provider-specific Tool Pack that declares `provider`, `transport`, and the
provider-neutral contract it `implements`. The adapter changes command translation, not lifecycle
authority. Adapter discovery records whether its executable is available; installation and
invocation remain separate explicit actions. Bundled adapters implement `ci-cd` and
`work-management` for GitHub through `gh`, plus `cloud-infrastructure` through Terraform CLI.
A partial adapter lists `implements-operations`; it must contain exactly that conforming subset and
cannot be invoked for omitted operations. AWS and Google Cloud inventory use this form for read-only
resource discovery.
An adapter may be distributed but unavailable in the current environment. `runtime_available`
reflects executable discovery only. A checked adapter additionally reports its detected version and
whether it meets the manifest's minimum runtime version. Neither result implies authentication,
installation, authority, or a successful provider call. The Jira adapter demonstrates the absent
state when ACLI is not installed.

A **Tool Run** binds the pack and operation to an assigned actor, swarm, optional work, and input map.
It may remain `prepared` for external delegation or be launched locally. `RUN.md` persists attribution
and command metadata, optional actor authentication evidence, while `RESULT.md` captures status,
output, and exit code.

The bundled **Work Management Tool Pack** separates `issue.read`, `issue.write`, and
`issue.transition` authority behind a stable `workctl` interface. External ticket state and Agora
work state remain independent records; synchronization requires explicit governed operations.

The bundled **CI/CD Tool Pack** separates routine inspection and execution from destructive
cancellation and deployment creation. A project may combine role capability with an operation-level
approval requirement; both must pass before a guarded deployment is prepared.

The bundled **Knowledge Base Tool Pack** grants reading, drafting, publication, and archival as four
separate authorities. Remote publication can become an artifact or evidence reference, but it never
replaces Agora's local work and governance state.

The bundled **Cloud Infrastructure Tool Pack** makes inspection, planning, deployment, and
destruction separate authorities. A plan identity connects review evidence to apply without making
remote provider state the Agora source of truth.

The bundled **Observability Tool Pack** separates signal reads, incident updates, and incident
resolution. External resolution is provider state; health results become durable Agora evidence only
when explicitly recorded under the active lifecycle.

## Standard

A standard is a versioned, provider-neutral rule enabled by `.agora/STANDARDS.md`. It applies across
human and agentic actors and may be enforced by validators referenced from Tool Pack `input-rules`.
Agora currently registers `conventional-commits/v1.0.0`; the bundled repository commit operation
validates that rule before preparing or executing Git.

## Registry

A registry is a named Markdown catalog containing zero or more Method Pack directories and Tool Pack
directories, with at least one pack overall. A registry has bundled, user, or project scope. It is a
reviewed source snapshot; installed packs remain ordinary local copies and do not depend on the
registry after installation.

When pack ids collide, project registry provenance precedes user provenance, which precedes the
bundled distribution. Explicit registry selection overrides inference while preserving pack
validation and destination-scope overwrite rules.

Dependencies may resolve across visible registries, but installed copies remain bound to their
target scope. Replacing one pack is rejected when the prospective version would break another
installed pack.

A **Pack Source** is installer-owned Markdown attached to a catalog-installed pack. It records the
pack and registry versions, registry scope and source, published tree checksum, and installation
time. A **Pack Update** compares that immutable source evidence with the current installed tree and
visible catalog, produces a dependency-first preview, and changes files only when application is
explicit. Local amendments are visible divergence rather than silent loss.

A **Pack Update History** is a per-pack transition from the previous installed version and actual
checksum to a selected catalog version and published checksum. A **Pack Composition Lock** is the
sorted projection of every Method and Tool Pack in one scope, including its actual checksum and
optional source identity. Histories explain change; the lock identifies current state.

A **Pack Removal** is an immutable scope-level record of an applied composition subtraction. It
identifies the requested pack, every explicitly pruned unused dependency, their last versions,
actual checksums, optional registries, and the removal timestamp. The pack directories represent
current state; the removal record and Git preserve why they disappeared.

A remote registry index publishes one or more semantic releases. Each release identifies an archive,
mandatory SHA-256, and optional Ed25519 signature plus key id. After verification Agora installs the
same local snapshot contract and adds a generated source record containing immutable provenance.

A registry trust key authorizes one Ed25519 public key id for one registry. Its user or project scope,
fingerprint, active or revoked status, and optional replacement are durable Markdown. Rotation adds a
new identity before revoking the previous identity; it never overwrites key history.

A registry update is a forward-only transition between immutable semantic releases. Preview state is
ephemeral; each applied transition persists its previous and target versions, checksums, index,
signature result, and timestamp under the installed registry. Updating the catalog does not update a
Method Pack or Tool Pack already copied into another scope.

## Environment

IDE, CLI, runner, and cloud agent are execution environments. They do not own Agora state. Every
environment reads and writes the same workspace protocol and synchronizes through Git.

## Model configuration

Provider and model identify the selected execution environment. They are strings in configuration,
not a closed list or a core SDK dependency. Changing an LLM must not change actor identity, workflow
state, artifacts, or governance history.

An actor may override the project integration, provider, and model. `agora start` resolves the
effective runtime, persists a session context, detects the external executable, and optionally
delegates execution to it. Agora provides context through files and environment variables rather
than invoking a model SDK.

## Session

A session binds an assigned actor, its active roles, a swarm, optional work, and effective runtime.
`SESSION.md` records the selection and launch result; `CONTEXT.md` lists the project, method, roles,
work, related delegations, policies, and operating rules the external agent must read. An
authenticated launch binds the runtime, exact command, and context digest to the actor's signature;
the completed session retains public verification evidence. Conversation history remains external
unless a material outcome is persisted in Agora files.

## Operational view and validation

An operational view is a computed projection of current Markdown records. Status counts, filtered
lists, and event queries are never persisted as parallel state and can always be reconstructed.

A validation issue identifies a severity, stable code, source path, and diagnostic message. A
validation report counts successfully inspected domain records and aggregates every issue found in
one pass. Errors make the report fail; warnings describe reviewable conditions without invalidating
the workspace. Validation is read-only and does not infer or repair missing state.
