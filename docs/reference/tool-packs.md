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
version-command: ["--version"]
minimum-runtime-version: "1.4.0"
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
| `version-command` | Optional structured CLI arguments used only for a local version probe |
| `minimum-runtime-version` | Optional numeric `MAJOR.MINOR.PATCH`; requires `version-command` |
| `authentication-reference` | Optional non-secret reference to external authentication |
| `timeout-seconds` | Optional direct-process timeout from 1 to 3600; defaults to 300 |
| `max-output-bytes` | Optional combined captured output limit from 1 to 10,485,760; defaults to 1,048,576 |
| `provider` | Adapter-only provider slug; requires `transport` and `implements` |
| `transport` | Adapter-only execution transport; currently `cli` |
| `implements` | Adapter-only id of the provider-neutral Tool Pack contract |
| `implements-operations` | Optional non-empty subset implemented by a deliberately partial adapter |

The executable is resolved by the environment when `--launch` is used. A prepared invocation does
not require it to be installed. Version metadata must be declared as a pair. When present, live
launch requires a successful compatible probe, while preparation and installation remain offline.

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
| `input-values` | Optional map restricting a declared input to explicit allowed strings |
| `approval-role` | Optional role whose approval must exist on the selected work |
| `result-kind` | Optional artifact kind describing the captured result |
| `environment-required` | Optional boolean requiring a governed project environment |

Agora never invokes a shell. It substitutes each `{input}` inside its argument and sends the result
as one process argument, so spaces or punctuation do not become new commands. Unknown inputs,
missing inputs, and undeclared placeholders are rejected.

Input rules and allowed values validate domain-specific values before `RUN.md` is created or an
executable is launched. The bundled rule registry currently contains
`conventional-commits/v1.0.0`; unknown rule ids, undeclared inputs, empty allowed-value arrays, and
duplicate allowed values make the Tool Pack invalid. Use `input-values` whenever an input occupies a
subcommand or mode position:

```markdown
input-values: {"state":["close","reopen"]}
```

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
allowed-environments: ["integration", "staging"]
---
```

An invocation requires a registered actor, an active swarm assignment, and an assigned role that
contains the operation capability. Tool installation alone grants no actor permission.
When an environment is selected, one assigned role must grant both the capability and that
environment, and `.agora/environments/<id>.md` must also allow the capability. See
[Environment permissions](../guides/environment-permissions.md).

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
`AGORA_ACTOR`, `AGORA_SWARM`, optional `AGORA_WORK`, and optional `AGORA_ENVIRONMENT`. Agora captures
standard output, standard error, status, and exit code in `RESULT.md`, and appends project and work
events. A non-zero exit is recorded before the CLI reports failure. Exit code `124` denotes an Agora
timeout and `125` denotes an output limit violation. Both limits and the selected environment are
copied into `RUN.md` and included in signed actor authorizations.

These portable direct-process limits do not restrict filesystem, network, syscalls, credentials,
memory, CPU, or detached descendants. Use a restricted external runner when those boundaries are
required. See [Portable Tool execution boundaries](../guides/execution-boundaries.md).

Credentials, tokens, cookies, and cloud identities must remain in the external CLI, keychain,
workload identity, or secret manager. Do not declare them as Tool Pack inputs because inputs and
commands are intentionally durable.

## Ecosystem patterns

Keep capabilities stable even when a project changes vendors:

| System category | Example capabilities | Typical durable result |
| --- | --- | --- |
| Issue tracking | `issue.read`, `issue.write`, `issue.transition` | `ticket` |
| Repository governance | `repository.governance.read` | `repository-ruleset` |
| Code review | `review.read`, `review.write`, `review.decide`, `review.merge` | `review` |
| CI/CD | `ci.read`, `ci.run`, `deployment.create` | `test-report`, `build`, `deployment` |
| Releases | `release.read`, `release.publish` | `release`, `release-verification` |
| Security | `security.read` | `security-alert-list` |
| Portfolio | `portfolio.read`, `portfolio.write` | `portfolio-project`, `portfolio-item` |
| Documentation | `docs.read`, `docs.write`, `docs.publish` | `documentation` |
| Cloud | `cloud.read`, `cloud.plan`, `cloud.deploy` | `plan`, `deployment` |
| Observability | `observability.read`, `incident.write` | `metric-report`, `incident` |
| Communication | `message.read`, `message.write` | `message` |

A team can point `executable` at a vendor CLI or at a reviewed internal wrapper that normalizes
multiple vendors. The Method Pack continues to grant `issue.read` or `ci.run`, not vendor product
names, so changing Jira, repository host, CI service, or cloud does not rewrite lifecycle policy.

Reviewed adapters bundled separately from the provider-neutral packs can be discovered and
installed explicitly:

```bash
agora tool adapter list --available
agora tool adapter list --check
agora tool adapter list --compatible
agora tool adapter install --id github-actions --scope project
agora tool adapter install --id github-projects --scope project
agora tool adapter install --id github-releases --scope project
agora tool adapter install --id github-repository-governance --scope project
agora tool adapter install --id github-security --scope project
agora tool adapter install --id gitlab-ci --scope project
agora tool adapter install --id gitlab-issues --scope project
agora tool adapter install --id gitlab-merge-requests --scope project
agora tool adapter install --id terraform --scope project
agora tool adapter install --id jira --scope project
agora tool adapter install --id twg-confluence --scope project
```

See [CLI-first ecosystem adapters](../guides/cli-first-adapters.md) for transport selection,
manifest metadata, and the MCP boundary.

A full adapter omits `implements-operations` and must conform to every operation in the referenced
contract. A partial adapter lists its exact subset:

```markdown
implements: "cloud-infrastructure"
implements-operations: ["list-resources","inspect-resource"]
```

Its Tool Pack must contain exactly those operations. Installation and `agora validate` reject
unknown, missing, or extra operations and any capability, risk, required-input, or result-kind drift.

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

The bundled `ci-cd` pack defines a stable `cictl` interface. Routine inspection uses `ci.read` and
pipeline triggering uses `ci.run`; destructive cancellation uses `ci.cancel`, while deployment uses
`deployment.create`. No bundled role receives the latter two capabilities. See the
[CI/CD integration guide](../guides/ci-cd-integrations.md) and its
[approval-focused sample](../../samples/ci-cd/README.md).

The bundled `knowledge-base` pack exposes a stable `docsctl` interface for Confluence, Notion, and
internal documentation services. Reads use `docs.read`, drafts use `docs.write`, publication uses
`docs.publish`, and destructive archival uses `docs.archive`. The latter two are not granted by
default. See the [knowledge-base integration guide](../guides/knowledge-base-integrations.md) and
[publication sample](../../samples/knowledge-base/README.md).

The bundled `cloud-infrastructure` pack defines a stable `cloudctl` interface. Inspection uses
`cloud.read`, non-mutating plans use `cloud.plan`, apply uses `cloud.deploy`, and destruction uses
`cloud.destroy`. Apply and destruction have no default role authority. See the
[cloud integration guide](../guides/cloud-integrations.md) and
[guarded apply sample](../../samples/cloud-infrastructure/README.md).

The bundled `observability` pack uses `observectl` for bounded health, metric, and log reads plus
incident creation and updates. Resolution uses the separate `incident.resolve` capability and has no
default authority. See the [observability integration guide](../guides/observability-integrations.md)
and [incident sample](../../samples/observability/README.md).
