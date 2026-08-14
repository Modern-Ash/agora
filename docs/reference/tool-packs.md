# Tool Pack reference

A Tool Pack is a provider-neutral Markdown contract that exposes selected operations from an
external CLI. It lets Agora govern repository, issue tracker, CI/CD, documentation, cloud,
observability, and communication tools without importing their SDKs or storing credentials.

## Directory contract

```text
my-tool/
  TOOL.md
  operations/
    view-issue.md
    create-issue.md
```

Both `TOOL.md` and at least one operation file are required.

## Tool manifest

```markdown
---
schema: "agora/tool/v1"
id: "issue-tracker"
name: "Team issue tracker"
version: "1.0.0"
dependencies: []
category: "issue-tracker"
executable: "tracker-cli"
authentication-reference: "tracker-cli-profile"
---

# Team issue tracker

Describe installation, environment, and governance expectations here.
```

| Attribute | Contract |
| --- | --- |
| `schema` | Must be `agora/tool/v1` |
| `id` | Lowercase Agora slug |
| `name` | Non-empty display name |
| `version` | Numeric `MAJOR.MINOR.PATCH`; omitted legacy versions resolve as `0.0.0` |
| `dependencies` | Optional array of version-constrained Method or Tool Pack references |
| `category` | Provider-neutral lowercase slug such as `repository` or `ci` |
| `executable` | One executable name or path; never a shell expression |
| `authentication-reference` | Optional non-secret reference to external authentication |

The executable is resolved by the environment when `--launch` is used. A prepared invocation does
not require it to be installed.

Dependencies use the same manifest and resolver contract as Method Packs. See
[Pack dependencies](../guides/pack-dependencies.md).

## Operation manifest

```markdown
---
schema: "agora/tool-operation/v1"
id: "view-issue"
name: "View an issue"
capability: "issue.read"
risk: "read"
arguments: ["issue","view","{issue}","--format","json"]
inputs: ["issue"]
input-rules: {}
result-kind: "ticket"
---

# View an issue

Returns one issue without modifying the tracker.
```

| Attribute | Contract |
| --- | --- |
| `schema` | Must be `agora/tool-operation/v1` |
| `id` | Unique lowercase operation slug within the pack |
| `name` | Non-empty display name |
| `capability` | Provider-neutral permission such as `issue.read` or `ci.run` |
| `risk` | `read`, `write`, or `destructive` |
| `arguments` | Structured argument array passed directly to the executable |
| `inputs` | Required input ids; every id must appear as an argument placeholder |
| `input-rules` | Optional map from a declared input to a registered versioned validator |
| `approval-role` | Optional role whose approval must exist on the selected work |
| `result-kind` | Optional artifact kind describing the captured result |

Agora never invokes a shell. It substitutes each `{input}` inside its argument and sends the result
as one process argument, so spaces or punctuation do not become new commands. Unknown inputs,
missing inputs, and undeclared placeholders are rejected.

Input rules validate domain-specific values before `RUN.md` is created or an executable is launched.
The bundled registry currently contains `conventional-commits/v1.0.0`; unknown rule ids and rules for
undeclared inputs make the Tool Pack invalid.

`risk` is durable classification for policy and review. Authority comes from the operation's exact
capability and, when configured, `approval-role`. A destructive operation should use a dedicated
capability that no bundled role receives by default.

## Role permissions

Method Pack roles grant tool authority separately from lifecycle actions:

```markdown
---
schema: "agora/role/v1"
id: "developer"
required-capabilities: ["implementation"]
allowed-actor-kinds: ["human", "ai-agent", "swarm"]
allowed-actions: ["work.transition", "artifact.add", "evidence.add"]
allowed-tool-capabilities: ["repository.read", "repository.write", "ci.read", "ci.run"]
---
```

An invocation requires a registered actor, an active swarm assignment, and an assigned role that
contains the operation capability. Tool installation alone grants no actor permission.

## Install and inspect

Install for reuse from the Agora home:

```bash
agora tool install --source ./issue-tracker --scope user
```

Install into one initialized project:

```bash
agora tool install --source ./issue-tracker --scope project
agora tool show --tool issue-tracker
```

New projects receive bundled packs first and user packs second. Project Tool Packs live under
`.agora/tools/<tool-id>` and may be reviewed or customized like Method Packs. Use `--force` only when
replacement is intentional, then inspect the Git diff.

Tool Packs may also be selected from an installed registry:

```bash
agora pack search --kind tool --registry team-catalog
agora pack install --kind tool --id issue-tracker \
  --registry team-catalog --scope project
```

See [Pack registries](../guides/pack-registries.md) for source validation and collision precedence.
Catalog-installed copies persist provenance and support explicit preview-first upgrades; see
[Pack updates](../guides/pack-updates.md).

## Prepare an invocation

```bash
agora tool invoke \
  --id inspect-agora-42 \
  --tool issue-tracker \
  --operation view-issue \
  --actor delivery-agent \
  --swarm payment-delivery \
  --work idempotency \
  --input issue=AGORA-42
```

Preparation validates the contract, assignment, capability, inputs, and approval policy, then writes
`.agora/tool-runs/inspect-agora-42/RUN.md`. It does not contact the external system. An IDE, CI job,
or cloud worker can use that durable record for delegated execution.

## Launch and capture a result

Add `--launch` to execute the structured command in the project root:

```bash
agora tool invoke \
  --id inspect-agora-42 \
  --tool issue-tracker \
  --operation view-issue \
  --actor delivery-agent \
  --swarm payment-delivery \
  --work idempotency \
  --input issue=AGORA-42 \
  --launch
```

The child process inherits its normal environment plus `AGORA_PROJECT`, `AGORA_TOOL_RUN`,
`AGORA_ACTOR`, `AGORA_SWARM`, and optional `AGORA_WORK`. Agora captures standard output, standard
error, status, and exit code in `RESULT.md`, and appends project and work events. A non-zero exit is
recorded before the CLI reports failure.

Credentials, tokens, cookies, and cloud identities must remain in the external CLI, keychain,
workload identity, or secret manager. Do not declare them as Tool Pack inputs because inputs and
commands are intentionally durable.

## Ecosystem patterns

Keep capabilities stable even when a project changes vendors:

| System category | Example capabilities | Typical durable result |
| --- | --- | --- |
| Issue tracking | `issue.read`, `issue.write`, `issue.transition` | `ticket` |
| Repository hosting | `repository.read`, `pull-request.write` | `review` |
| CI/CD | `ci.read`, `ci.run`, `deployment.create` | `test-report`, `build`, `deployment` |
| Documentation | `docs.read`, `docs.write`, `docs.publish` | `documentation` |
| Cloud | `cloud.read`, `cloud.plan`, `cloud.deploy` | `plan`, `deployment` |
| Observability | `observability.read`, `incident.write` | `metric-report`, `incident` |
| Communication | `message.read`, `message.write` | `message` |

A team can point `executable` at a vendor CLI or at a reviewed internal wrapper that normalizes
multiple vendors. The Method Pack continues to grant `issue.read` or `ci.run`, not vendor product
names, so changing Jira, repository host, CI service, or cloud does not rewrite lifecycle policy.

## Bundled packs

Agora includes a `repository` pack backed by Git. It demonstrates read and write operations without
making Git special in the kernel:

```bash
agora tool invoke --id repo-status --tool repository --operation status \
  --actor developer --swarm delivery --launch

agora tool invoke --id inspect-main --tool repository --operation show-revision \
  --actor developer --swarm delivery --input revision=main --launch

agora tool invoke --id governed-commit --tool repository --operation commit \
  --actor developer --swarm delivery \
  --input message="feat(delivery): add governed result" --launch
```

The commit operation acts only on already staged files and validates its message against Conventional
Commits 1.0.0. Run the [governed tool sample](../../samples/tool-integration/README.md) for an
executable example.

Agora also includes `work-management`, a stable `workctl` interface for external issue trackers. Its
search and view operations require `issue.read`; create and comment require `issue.write`; transition
requires `issue.transition`. Configure a reviewed wrapper for Jira, Linear, or another provider
without changing those Method Pack capabilities. See the
[work-management integration guide](../guides/work-management-integrations.md) and its
[executable sample](../../samples/work-management/README.md).
