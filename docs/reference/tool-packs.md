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
| `category` | Provider-neutral lowercase slug such as `repository` or `ci` |
| `executable` | One executable name or path; never a shell expression |
| `authentication-reference` | Optional non-secret reference to external authentication |

The executable is resolved by the environment when `--launch` is used. A prepared invocation does
not require it to be installed.

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
| `approval-role` | Optional role whose approval must exist on the selected work |
| `result-kind` | Optional artifact kind describing the captured result |

Agora never invokes a shell. It substitutes each `{input}` inside its argument and sends the result
as one process argument, so spaces or punctuation do not become new commands. Unknown inputs,
missing inputs, and undeclared placeholders are rejected.

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

## Bundled repository pack

Agora includes a `repository` pack backed by Git. It demonstrates read and write operations without
making Git special in the kernel:

```bash
agora tool invoke --id repo-status --tool repository --operation status \
  --actor developer --swarm delivery --launch

agora tool invoke --id inspect-main --tool repository --operation show-revision \
  --actor developer --swarm delivery --input revision=main --launch
```

Run the [governed tool sample](../../samples/tool-integration/README.md) for an executable example.
