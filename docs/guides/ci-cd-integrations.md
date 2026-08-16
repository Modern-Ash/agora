# CI/CD integrations

Agora includes a provider-neutral `ci-cd` Tool Pack for inspecting pipelines, triggering verified
work, cancelling runs, and creating deployments. The pack governs commands and attribution while an
external adapter handles GitHub Actions, GitLab CI/CD, Jenkins, or an internal delivery platform.

## Stable operation contract

New projects receive `.agora/tools/ci-cd` with this interface:

| Operation | Capability | Risk | Inputs | Result kind |
| --- | --- | --- | --- | --- |
| `list-runs` | `ci.read` | read | `pipeline` | `pipeline-run-list` |
| `view-run` | `ci.read` | read | `run` | `pipeline-run` |
| `trigger` | `ci.run` | write | `pipeline`, `ref`, `parameters` | `pipeline-run` |
| `cancel-run` | `ci.cancel` | destructive | `run` | `pipeline-run` |
| `view-deployment` | `ci.read` | read | `deployment` | `deployment` |
| `create-deployment` | `deployment.create` | write | `environment`, `artifact` | `deployment` |

The default executable is `cictl`, a stable team-controlled adapter name. It accepts commands such
as:

```text
cictl run list --pipeline verify --output json
cictl pipeline trigger verify --ref main --parameters suite=all --output json
cictl deployment create --environment staging --artifact sha256:verified --output json
```

Agora invokes argument arrays directly without a shell. The adapter translates stable identities
such as `verify`, `run-42`, and `sha256:verified` into provider-specific workflows, job ids, and
artifacts.

Existing projects remain unchanged when the CLI is updated. Install the bundled pack explicitly:

```bash
agora pack install \
  --kind tool \
  --id ci-cd \
  --registry agora-bundled \
  --scope project
agora validate
```

Installation refreshes `PACKS.lock.md` but does not alter local Method Pack permissions.

## Native GitHub CLI adapter

When a developer already uses GitHub CLI, install the reviewed adapter instead of maintaining a
`cictl` wrapper:

```bash
agora tool adapter list --available
agora tool adapter install --id github-actions --scope project
```

Invoke `github-actions/list-runs`, `view-run`, `trigger`, `cancel-run`, `view-deployment`, or
`create-deployment`. The adapter calls `gh` directly, preserves the same provider-neutral
capabilities, and leaves authentication in the developer's existing GitHub CLI profile. Installing
it does not remove `ci-cd` or grant `ci.cancel` and `deployment.create`.

See [CLI-first ecosystem adapters](cli-first-adapters.md) for the selection policy and complete
examples.

## Default authority

Bundled Spec-Driven, Scrum, and Kanban roles already separate CI/CD authority:

| Role type | Granted capabilities |
| --- | --- |
| Developer or Delivery | `ci.read`, `ci.run` |
| Scrum Master or Flow Manager | `ci.read` |
| Product Owner, Service Request Manager, or Spec Owner | none by default |
| Every bundled role | no `ci.cancel` or `deployment.create` |

This makes routine verification usable while keeping cancellation and deployment opt-in. Installing
the pack never grants authority by itself.

## Trigger verified work

Prepare an attributable run without contacting the provider:

```bash
agora tool invoke \
  --id verify-main \
  --tool ci-cd \
  --operation trigger \
  --actor developer \
  --swarm release \
  --work release-candidate \
  --input pipeline=verify \
  --input ref=main \
  --input parameters=suite=all
```

Add `--launch` only in an environment with the reviewed `cictl` adapter and its external
authentication. Agora captures the command, output, error stream, exit code, and result kind under
`.agora/tool-runs` and appends attributable project and work events.

The `parameters` value is one durable adapter-defined string, not a secret channel. Use it for
non-sensitive selections such as `suite=all` or `region=test`; credentials and secret values must
remain in the provider's secret store or workload identity.

## Guard deployment with approval

A team must first grant `deployment.create` to the intended role in its local Method Pack. It can
then add an approval requirement to `operations/create-deployment.md`:

```markdown
---
schema: "agora/tool-operation/v1"
id: "create-deployment"
name: "Create a deployment"
capability: "deployment.create"
risk: "write"
environment-required: true
arguments: ["deployment","create","--environment","{environment}","--artifact","{artifact}","--output","json"]
inputs: ["environment","artifact"]
approval-role: "product-owner"
result-kind: "deployment"
---
```

After reviewing local pack amendments, refresh the composition lock:

```bash
agora pack lock --scope project
agora validate
```

The assigned actor still needs the exact capability. The selected work must also contain an approval
from the declared role before Agora prepares or launches the deployment. A production policy may use
a different role, stronger evidence gates, or a separately versioned Tool Pack operation.

## Adapt a provider

A reviewed `cictl` wrapper should:

1. accept only the declared `run`, `pipeline`, and `deployment` subcommands;
2. map stable pipeline and environment names to provider configuration;
3. invoke vendor CLIs with argument arrays, never concatenated shell strings;
4. return machine-readable output and preserve non-zero provider exit codes;
5. resolve credentials from the vendor CLI, workload identity, or secret manager;
6. redact tokens and sensitive provider output before it reaches durable results;
7. verify immutable artifact identities before creating a deployment.

For GitHub Actions, the adapter can map pipelines to workflows. For GitLab CI/CD, it can map them to
pipelines and jobs. For Jenkins, it can map them to approved jobs and build numbers. These mappings
belong in the adapter or a provider-specific pack, never in Agora's kernel.

If a provider cannot implement the stable interface, publish a team Tool Pack with different
argument arrays, a bumped semantic version, and the same provider-neutral capabilities.

## State ownership

Agora owns actor authority, approvals, evidence references, Tool Runs, and filesystem history. The
CI/CD provider owns remote run and deployment state. A successful external deployment is captured
evidence; it does not automatically satisfy acceptance criteria or transition Agora work. The active
Method Pack still controls lifecycle completion.

Run the executable provider and approval example:

```bash
uv run python samples/ci-cd/run.py
```
