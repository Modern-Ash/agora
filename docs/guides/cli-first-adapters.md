# CLI-first ecosystem adapters

Agora prefers a provider's native CLI when it is already part of the developer's working
environment. The CLI keeps its existing authentication, profiles, repository context, workload
identity, and audit controls. Agora adds lifecycle authority and durable evidence around that tool;
it does not replace the tool's configuration.

## Selection order

Use this order when connecting an external system:

1. A reviewed native CLI adapter when the provider CLI is installed and supports the required
   non-interactive operation.
2. A reviewed team CLI wrapper when several providers must expose one stable operation shape or the
   native CLI output needs redaction and normalization.
3. An MCP adapter when MCP exposes a required capability that is absent from the CLI or when the
   execution environment is already governed through an MCP host.

Transport selection never changes Method Pack authority. Roles continue to receive capabilities
such as `ci.read`, `issue.write`, `review.decide`, or `cloud.plan`, regardless of whether execution uses `gh`, `acli`,
`aws`, a team wrapper, or a future MCP bridge.

Agora never silently switches transports. Discovery is read-only, installation is explicit, and
each prepared `RUN.md` contains the exact executable and arguments that will run.

## Discover installed CLIs

List every reviewed adapter bundled with the installed Agora distribution:

```bash
agora tool adapter list
```

Only show adapters whose executable is currently available on `PATH`:

```bash
agora tool adapter list --available
```

Probe the versions of available CLIs, or return only compatible runtimes:

```bash
agora tool adapter list --check
agora tool adapter list --compatible
```

Plain discovery does not execute the CLI. `--check` runs only the structured version command from
the reviewed manifest with a five-second timeout. It reports `minimum_runtime_version`,
`runtime_version`, `runtime_compatible`, and a diagnostic detail. `--compatible` implies the check
and omits missing, old, failed, or unparseable runtimes. Neither mode contacts the provider,
inspects credentials, installs a pack, or grants authority.

Installation remains possible before a compatible runtime exists because it only materializes the
Markdown contract. Preparing a governed invocation also remains possible. A live `--launch` for a
pack with version requirements fails before `RUN.md` is written when the executable is missing, too
old, or cannot return a verifiable `MAJOR.MINOR.PATCH` version.

## Install an adapter

Install for all projects initialized from the current Agora home:

```bash
agora tool adapter install --id github-actions --scope user
```

Install only in the current project:

```bash
agora tool adapter install --id github-actions --scope project
agora tool show --tool github-actions
agora validate
```

Installation copies the reviewed Markdown Tool Pack and refreshes the corresponding
`PACKS.lock.md`. It does not replace the provider-neutral `ci-cd` pack and does not modify Method
Pack role permissions.

## GitHub Actions through `gh`

The GitHub Actions adapter implements the `ci-cd` capability contract directly through GitHub CLI:

| Operation | Native command family | Capability |
| --- | --- | --- |
| `list-runs` | `gh run list` | `ci.read` |
| `view-run` | `gh run view` | `ci.read` |
| `trigger` | `gh workflow run` | `ci.run` |
| `cancel-run` | `gh run cancel` | `ci.cancel` |
| `view-deployment` | `gh api` | `ci.read` |
| `create-deployment` | `gh api` | `deployment.create` |

Inspect a governed command without contacting GitHub:

```bash
agora tool invoke \
  --id inspect-verification-runs \
  --tool github-actions \
  --operation list-runs \
  --actor developer \
  --swarm delivery \
  --input pipeline=verify.yml
```

Execute it through the current `gh` profile:

```bash
agora tool invoke \
  --id inspect-verification-runs-live \
  --tool github-actions \
  --operation list-runs \
  --actor developer \
  --swarm delivery \
  --input pipeline=verify.yml \
  --launch
```

Run `gh auth status` separately before launch when authentication is uncertain. Tokens, hosts, and
profiles remain owned by GitHub CLI and must never be Tool Pack inputs.

## GitHub Issues through `gh`

The `github-issues` adapter implements `work-management` through native issue commands:

```bash
agora tool adapter install --id github-issues --scope project
agora tool invoke \
  --id close-reviewed-issue \
  --tool github-issues \
  --operation transition \
  --actor product-owner \
  --swarm delivery \
  --input issue=42 \
  --input state=close
```

Search and view use bounded JSON fields; create and comment supply all content non-interactively.
Transition maps the state into the native command position, so its manifest restricts the value to
`close` or `reopen`. Values such as `delete`, `edit`, or `transfer` are rejected before `RUN.md` is
created.

## GitLab Issues through `glab`

The `gitlab-issues` adapter implements an explicit subset of `work-management` through GitLab CLI
1.109.0 or newer:

```bash
agora tool adapter install --id gitlab-issues --scope project
agora tool invoke \
  --id inspect-gitlab-work \
  --tool gitlab-issues \
  --operation search \
  --actor developer \
  --swarm delivery \
  --input query="governance"
```

Search and view request bounded JSON. Comment uses a non-interactive message flag. Transition places
the requested state in a subcommand position, so the manifest permits only `close` or `reopen`.
Create is omitted because the native command cannot preserve the neutral contract's required
work-item `type`; Agora does not discard it or reinterpret it as a label.

## GitLab Merge Requests through `glab`

The `gitlab-merge-requests` adapter implements an explicit subset of `code-review` through GitLab
CLI 1.109.0 or newer:

```bash
agora tool adapter install --id gitlab-merge-requests --scope project
agora tool invoke \
  --id inspect-gitlab-review \
  --tool gitlab-merge-requests \
  --operation checks \
  --actor developer \
  --swarm delivery \
  --input review=42
```

View and checks request JSON, create supplies every field non-interactively without pushing, and
comment uses a native message flag. List is omitted because neutral states map to different native
flags. Approval cannot carry the required decision body, request-changes has no native decision,
and merge strategies need conditional flags; a reviewed team wrapper can normalize those gaps.

## GitHub Pull Requests through `gh`

The `github-pull-requests` adapter implements the provider-neutral `code-review` contract. It can
list and view reviews, create and comment on Pull Requests, inspect checks, and submit approval or
request-changes decisions. Merge remains a distinct `review.merge` capability granted to no bundled
role. See [Code-review integrations](code-review-integrations.md) for the complete flow.

## GitLab CI/CD through `glab`

The `gitlab-ci` adapter implements exact pipeline listing, inspection, and cancellation through
GitLab CLI 1.109.0 or newer:

```bash
agora tool adapter install --id gitlab-ci --scope project
agora tool invoke \
  --id inspect-gitlab-pipeline \
  --tool gitlab-ci \
  --operation view-run \
  --actor developer \
  --swarm delivery \
  --input run=12345
```

Pipeline reads are JSON and bounded. Inspection includes job details but not variables or logs.
Cancellation retains destructive risk and ungranted `ci.cancel` authority. Trigger and deployment
operations are omitted because the native CLI cannot bind every required neutral input; see
[CI/CD integrations](ci-cd-integrations.md).

## Jira through Atlassian CLI

The `jira` adapter implements the complete `work-management` contract through ACLI:

```bash
agora tool adapter install --id jira --scope project
agora tool invoke \
  --id inspect-agora-42 \
  --tool jira \
  --operation view \
  --actor developer \
  --swarm delivery \
  --input issue=AGORA-42
```

Search uses bounded JQL results and selected fields. View, create, and comment request JSON, while
transition supplies `--yes` to avoid an interactive confirmation after Agora authority has passed.
Jira still applies its own workflow permissions, conditions, and validators.

The adapter is distributed even when ACLI is absent. In that case it appears in
`agora tool adapter list` with `runtime_available: false`, is omitted by `--available`, and can still
prepare durable commands without `--launch`. Agora never installs ACLI or initiates authentication.

## Confluence through Atlassian TWG CLI

The `twg-confluence` adapter implements an explicit page-lifecycle subset of `knowledge-base`
through Atlassian Teamwork Graph CLI 1.2.5 or newer:

```bash
agora tool adapter install --id twg-confluence --scope project
agora tool invoke \
  --id inspect-runbook \
  --tool twg-confluence \
  --operation view \
  --actor developer \
  --swarm delivery \
  --input document=12345
```

The full `view` result includes HTML, metadata, and an opaque snapshot token. Pass that token as
`snapshot-token` when preparing an `update`; this preserves TWG's optimistic concurrency check and
rejects a stale draft instead of overwriting a concurrent edit. Creates are page drafts. Publication
and archival remain distinct `docs.publish` and `docs.archive` capabilities granted to no bundled
role.

The adapter deliberately omits `search`. TWG exposes natural-text search without a Confluence-space
filter and CQL search where safe quoting requires a translation wrapper. Agora does not interpolate
untrusted text into CQL or pretend that an Atlassian site is a Confluence space. Use the neutral
`knowledge-base` pack with a reviewed `docsctl` wrapper when all six operations are required.

Agora never installs `twg`, runs OAuth login, or changes its permissions. Installation and
authentication follow Atlassian's official
[TWG CLI setup](https://developer.atlassian.com/cloud/twg-cli/getting-started/installation/), while
live launch still requires `agora tool adapter list --check` to confirm a compatible local
version.

## Terraform through its native CLI

The `terraform` adapter implements `cloud-infrastructure` without importing Terraform or cloud SDKs:

| Operation | Native command family | Capability |
| --- | --- | --- |
| `list-resources` | `terraform state list` | `cloud.read` |
| `inspect-resource` | filtered `terraform state list` | `cloud.read` |
| `plan` | `terraform plan -out` | `cloud.plan` |
| `apply-plan` | `terraform apply <saved-plan>` | `cloud.deploy` |
| `destroy-resource` | targeted `terraform destroy` | `cloud.destroy` |

Install and prepare a saved plan:

```bash
agora tool adapter install --id terraform --scope project
agora tool invoke \
  --id plan-staging \
  --tool terraform \
  --operation plan \
  --actor developer \
  --swarm delivery \
  --environment staging \
  --input environment=infra/staging \
  --input change=plans/staging.tfplan
```

The governed `staging` environment must allow `cloud.plan`. The `environment` input is the reviewed
Terraform root-module directory. The `change` input is the saved plan path, not free-form change
text. Saved plan files can contain sensitive configuration and must remain outside Git or follow the
project's protected artifact policy. Applying a saved plan and targeted destruction retain their
separate capabilities and are not granted to bundled roles.

## Partial AWS and Google Cloud inventory

AWS CLI and gcloud do not expose one provider-wide plan/apply abstraction equivalent to Terraform.
Agora therefore includes honest read-only adapters instead of mapping deployment capabilities to
unrelated commands:

```bash
agora tool adapter install --id aws-resource-inventory --scope project
agora tool adapter install --id gcp-asset-inventory --scope project
```

Both declare:

```markdown
implements: "cloud-infrastructure"
implements-operations: ["list-resources","inspect-resource"]
```

The AWS adapter uses the Resource Groups Tagging API and treats `environment` as a Region. That API
returns tagged or previously tagged resources, so the result is explicitly not a complete account
inventory. The Google Cloud adapter uses Cloud Asset Inventory, treats `environment` as a project,
folder, or organization scope, limits results, and persists only a bounded field projection.

Neither adapter contains `plan`, `apply-plan`, or `destroy-resource`. Calling those operation ids
fails as unsupported rather than falling through to another tool or transport.

## Adapter contract

A CLI adapter is an ordinary Tool Pack with three additional manifest attributes:

```markdown
---
schema: "agora/tool/v1"
id: "github-actions"
name: "GitHub Actions CLI adapter"
version: "1.0.0"
category: "ci"
executable: "gh"
version-command: ["--version"]
minimum-runtime-version: "2.45.0"
provider: "github"
transport: "cli"
implements: "ci-cd"
---
```

`provider` identifies the external ecosystem, `transport` identifies how operations execute, and
`implements` identifies the provider-neutral Tool Pack contract. All three are required together.
`version-command` is a structured argument array appended to `executable`, and
`minimum-runtime-version` is its required numeric version; they must appear together. The current
executable adapter transport is `cli`. Full adapters must preserve every operation; partial adapters
declare `implements-operations`. Installation verifies the exact claimed set with the same
capability, risk, required inputs, and result kind. Adapters may add provider context inputs but
cannot weaken the contract.

Adapter operations must remain shell-free, non-interactive, credential-free, and bounded. Output
that may contain secrets or excessive logs should be filtered by the native CLI or a reviewed Python
wrapper before Agora persists it.

## MCP boundary

MCP is an integration transport, not Agora's source of truth. An MCP implementation must preserve
the same operation capability, risk, approval, attribution, and durable result semantics as a CLI
adapter. Until a native MCP execution transport is added to the kernel, teams may expose MCP through
a reviewed external CLI bridge; Agora must not embed an MCP SDK, server credentials, or opaque tool
selection in Method Packs.
