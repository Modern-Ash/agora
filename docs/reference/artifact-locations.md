# Documentation and artifact locations

Agora uses Markdown for both explanatory documentation and operational records. The file extension
does not determine the role of a file; its directory, schema, ownership, and lifecycle do.

## Classification

| Class | Source location | Materialized location | Consumer | Mutability |
| --- | --- | --- | --- | --- |
| Product documentation | `docs/` | Not materialized | Humans and contributors | Edited with the product |
| Plugin run output | `docs/superpowers/` | Plugin-owned | Contributors and the originating plugin | Managed by plugin runs |
| Portable agent commands | `packs/commands/` | `.agora/commands/` | Humans, agents, and generic runners | Customized per project |
| Project protocol sources | `packs/scaffold/` | `.agora/` | Every project participant | Customized per project |
| Method Pack sources | `packs/methods/` | `.agora/methods/` | Kernel, humans, and agents | Installed and versioned |
| Tool Pack sources | `packs/tools/` | `.agora/tools/` | Kernel, agents, and tool runners | Installed and versioned |
| Reviewed CLI adapters | `packs/adapters/` | `.agora/tools/` when installed | Kernel and native CLIs | Explicitly installed |
| Environment adapters | Generated from portable commands | `.agents/skills/` or `.claude/commands/` | Codex or Claude | Generated, then reviewable |
| Durable collaboration state | Created by Agora commands | `.agora/` | Kernel, humans, and agents | Changed only through governed operations |
| Product outputs | Project files or external systems | Referenced from `artifacts.md` | Humans, agents, and lifecycle gates | Owned by their producing system |

`docs/superpowers/` is intentionally retained as the output location of Superpowers plugin runs. It
is not normative Agora protocol, a bundled Method Pack, or project runtime state.

```mermaid
flowchart LR
    DOC[docs/] --> READER[Human understanding]
    T[packs/] --> INIT[agora init or install]
    INIT --> STATE[.agora durable protocol and state]
    STATE --> CODEX[.agents/skills]
    STATE --> CLAUDE[.claude/commands]
    STATE --> GENERIC[Generic runner context]
    CODEX --> WORK[Governed work]
    CLAUDE --> WORK
    GENERIC --> WORK
    WORK --> REF[artifacts.md and evidence.md references]
    REF --> PRODUCT[Repository or external system outputs]
```

## Distribution sources

The Markdown under `packs/` is source material shipped with the Python distribution. It is not
the state of a governed project until Agora copies or installs it into a project or user scope.

### Portable commands

[`packs/commands/`](../../packs/commands/) contains model-independent instructions such as `objective`, `specify`,
`execute`, `review`, and `complete`. Initialization always copies them to:

```text
.agora/commands/<command>.md
```

The selected integration adds one environment-specific projection:

```text
Codex:   .agents/skills/agora-<command>/SKILL.md
Claude:  .claude/commands/agora.<command>.md
Generic: .agora/commands/<command>.md
```

The portable `.agora/commands/` file is authoritative. `agora validate` detects drift between it and
the Codex or Claude projection.

### Shared project protocol

[`packs/scaffold/`](../../packs/scaffold/) provides the initial collaboration contract:

```text
.agora/project.md
.agora/constitution.md
.agora/PROTOCOL.md
.agora/STANDARDS.md
.agora/PACKS.lock.md
.agora/tools/TOOLS.md
```

These files are operational inputs. Agents read them before acting; the Python kernel validates the
structured portions; the repository and Git preserve review history.

### Method and Tool Packs

[`packs/methods/`](../../packs/methods/) contains example lifecycle contracts. Their `METHOD.md`, roles, gates, and
transitions define allowed work states and actions. Scrum, Kanban, and spec-driven development are
bundled examples rather than privileged kernel workflows.

[`packs/tools/`](../../packs/tools/) contains provider-neutral operation contracts.
[`packs/adapters/`](../../packs/adapters/) contains
reviewed translations to native provider CLIs. Finding a CLI on `PATH` never installs its adapter or
grants its capabilities.

## Durable project records

Agora creates current collaboration state under `.agora/`. Common records include:

Newly created swarms get a directory prefixed with a sequential number (`001-`, `002-`, ...), so
`.agora/swarms/` sorts in creation order at a glance — e.g. `.agora/swarms/001-delivery/`. The
logical swarm id stays unprefixed (`--swarm delivery` keeps working unchanged); only the directory
name carries the number. Swarm directories created before this feature shipped are left unnumbered
and continue to resolve normally — every path lookup goes through one resolver that accepts either
form.

```text
.agora/actors/<actor>/ACTOR.md
.agora/swarms/<swarm>/SWARM.md
.agora/swarms/<swarm>/work/<work>/WORK.md
.agora/swarms/<swarm>/work/<work>/clarifications.md
.agora/swarms/<swarm>/work/<work>/checklists/<checklist>.md
.agora/swarms/<swarm>/work/<work>/consistency/<report>.md
.agora/swarms/<swarm>/work/<work>/gherkin/<criterion>.feature
.agora/swarms/<swarm>/work/<work>/artifacts.md
.agora/swarms/<swarm>/work/<work>/evidence.md
.agora/swarms/<swarm>/work/<work>/approvals.md
.agora/actions/<action>/ACTION.md
.agora/delegations/<delegation>/DELEGATION.md
.agora/sessions/<session>/SESSION.md
.agora/sessions/<session>/CONTEXT.md
.agora/sessions/<session>/PROGRESS.md
.agora/sessions/<session>/RESULT.md
.agora/swarms/<swarm>/work/<work>/usage/<usage>/USAGE.md
.agora/swarms/<swarm>/work/<work>/budget-amendments/<amendment>/AMENDMENT.md
.agora/tool-runs/<run>/RUN.md
.agora/tool-runs/<run>/RESULT.md
```

These are neither manuals nor disposable prompts. They are durable governed records shared through
the filesystem and Git. Chat history is not a substitute for them.

`clarifications.md` is append-only, while each checklist is an attributed Markdown task list.
Consistency and Gherkin files are generated advisory work products. Their artifact rows and source
files retain canonical input hashes when provenance is available, allowing `agora work traceability`
and `agora validate` to detect stale output. Missing hashes on legacy records are warnings rather
than parse failures.

`RUN.md` exists after preparation. `RESULT.md` exists only after launch reaches a terminal outcome.
Use `agora tool result --run <run>` to read their validated typed view; do not treat ad hoc terminal
logs as a replacement for the durable record.

## Work products versus Agora records

Agora normally references produced work rather than copying opaque content. A specification, source
tree, test report, ticket, build, deployment, or external page remains in its owning repository or
provider. The work item's `artifacts.md` records its kind, URI, optional content SHA-256, producer,
and timestamp. Its `evidence.md` records verification outcomes, artifact references, and the durable
digest observed for each relationship. Remote content stays provider-owned and is never fetched
automatically. `budget-amendments/*/AMENDMENT.md` preserves each authorized change to a child's
current budget without rewriting the historical decision.

Generated `consistency-report` and `gherkin-feature` artifacts follow the same rule. Generation does
not make them lifecycle requirements; a work item's `required-artifacts` or a Method Pack gate must
name the kind to make it binding. Clarifications and checklists are not artifact kinds and do not
satisfy a gate.

The catalog at `.agora/artifacts/ARTIFACTS.md`, sourced from
`packs/scaffold/artifacts/ARTIFACTS.md`, defines common artifact kinds. It is a project policy
catalog, not a container for the product bytes.

## Repository-specific agent instructions

The root `AGENTS.md` governs coding agents contributing to the Agora repository itself. It is not
copied by `agora init` and is not part of the portable project protocol. Governed projects receive
their instructions from `.agora/PROTOCOL.md`, the active Method Pack, role contracts, portable
commands, and the selected environment adapter.

## Practical rule

Use this decision order when reading a Markdown file:

1. Under `docs/`: explanatory material, except explicitly plugin-owned run output.
2. Under `packs/`: distribution source for a protocol, pack, command, or reviewed adapter.
3. Under `.agora/`: authoritative project policy or durable collaboration state.
4. Under `.agents/` or `.claude/`: environment projection of a portable agent command.
5. Referenced by `artifacts.md`: a work product owned by its repository or external system.
