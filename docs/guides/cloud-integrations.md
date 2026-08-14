# Cloud integrations

Agora includes a provider-neutral `cloud-infrastructure` Tool Pack for inspecting resources,
planning changes, applying reviewed plans, and destroying resources. A reviewed adapter can connect
the same contract to AWS, Azure, Google Cloud, Terraform, OpenTofu, Pulumi, or an internal platform.

## Stable operation contract

New projects receive `.agora/tools/cloud-infrastructure` with this interface:

| Operation | Capability | Risk | Inputs | Result kind |
| --- | --- | --- | --- | --- |
| `list-resources` | `cloud.read` | read | `environment` | `cloud-resource-list` |
| `inspect-resource` | `cloud.read` | read | `resource`, `environment` | `cloud-resource` |
| `plan` | `cloud.plan` | read | `environment`, `change` | `infrastructure-plan` |
| `apply-plan` | `cloud.deploy` | write | `plan`, `environment` | `cloud-deployment` |
| `destroy-resource` | `cloud.destroy` | destructive | `resource`, `environment` | `cloud-destruction` |

The default executable is `cloudctl`, a stable team-controlled adapter name:

```text
cloudctl resource inspect service/api --environment staging --output json
cloudctl change plan --environment staging --change increase-api-capacity --output json
cloudctl change apply plan-42 --environment staging --output json
```

Agora invokes argument arrays directly without a shell. The adapter maps stable environment,
resource, change, and plan identities to provider-specific accounts, subscriptions, projects,
regions, stacks, or workspaces.

Existing projects remain unchanged when the CLI is updated. Install the bundled pack explicitly:

```bash
agora pack install \
  --kind tool \
  --id cloud-infrastructure \
  --registry agora-bundled \
  --scope project
agora validate
```

Installation refreshes `PACKS.lock.md` but preserves local Method Pack permissions.

## Native Terraform CLI adapter

When Terraform CLI is already configured, install the reviewed native adapter:

```bash
agora tool adapter list --available
agora tool adapter install --id terraform --scope project
```

The adapter treats `environment` as a Terraform root-module directory. `plan` writes the supplied
`change` path with `terraform plan -out`; `apply-plan` consumes that exact saved plan. Saved plans may
contain sensitive values and must remain outside Git or use the project's protected artifact store.
Agora persists the plan path and command, not the binary plan contents.

Resource inspection deliberately uses filtered `terraform state list` instead of `terraform state
show`, avoiding raw resource attributes in durable output. A team needing detailed attributes should
use a reviewed redacting wrapper. Applying and targeted destruction retain `cloud.deploy` and
`cloud.destroy`; installation grants neither.

## Default authority

Bundled methods use conservative cloud permissions:

| Role type | Granted capabilities |
| --- | --- |
| Developer or Delivery | `cloud.read`, `cloud.plan` |
| Scrum Master or Flow Manager | `cloud.read` |
| Product Owner or Service Request Manager | none by default |
| Every bundled role | no `cloud.deploy` or `cloud.destroy` |

Inspection and non-mutating plans can support ordinary delivery. Apply and destruction require an
explicit local grant. Installing the pack grants nothing by itself.

## Plan before apply

Prepare or launch a non-mutating plan:

```bash
agora tool invoke \
  --id plan-api-capacity \
  --tool cloud-infrastructure \
  --operation plan \
  --actor developer \
  --swarm release \
  --work capacity-change \
  --input environment=staging \
  --input change=increase-api-capacity \
  --launch
```

The adapter should return a stable immutable plan identity and enough evidence for review. Apply
must consume that identity rather than regenerate a change from free-form text.

The `change`, `plan`, environment, and resource values are durable inputs. They must not contain
credentials, private keys, secret values, or sensitive connection strings. Authentication belongs
to workload identity, the provider CLI, a keychain, or a secret manager.

## Guard apply with approval

Grant `cloud.deploy` only to the intended local role, then add an approval requirement to
`operations/apply-plan.md`:

```markdown
---
schema: "agora/tool-operation/v1"
id: "apply-plan"
name: "Apply an infrastructure plan"
capability: "cloud.deploy"
risk: "write"
arguments: ["change","apply","{plan}","--environment","{environment}","--output","json"]
inputs: ["plan","environment"]
approval-role: "product-owner"
result-kind: "cloud-deployment"
---
```

Review local pack amendments and refresh the composition lock:

```bash
agora pack lock --scope project
agora validate
```

The applying actor must hold `cloud.deploy`, and the selected work must contain the declared role's
approval. Production policies should additionally require the plan artifact, verification evidence,
and environment-specific gates before work completion.

`cloud.destroy` remains a separate destructive capability. Do not grant it merely because a role can
deploy. Teams should use a dedicated operation policy, stronger approvals, and recovery evidence.

## Adapt a cloud provider

A reviewed `cloudctl` wrapper should:

1. map each stable environment to an allowlisted account, subscription, project, region, and stack;
2. reject unknown or mismatched environment mappings before invoking a provider;
3. produce an immutable plan with a digest or provider revision and verify it again at apply time;
4. invoke provider CLIs with argument arrays rather than shell strings;
5. return machine-readable output and preserve non-zero provider exit codes;
6. obtain credentials from short-lived workload identity or an external secret system;
7. redact secrets, credentials, raw state, and sensitive provider metadata from durable output;
8. reject destructive plans on the non-destructive `plan` path when local policy requires it.

AWS, Azure, and Google Cloud adapters may translate stable resource ids into provider resource names.
Terraform, OpenTofu, or Pulumi adapters may translate environments into reviewed workspaces or
stacks. Provider commands, state backends, locking, and authentication belong in the adapter or a
provider-specific Tool Pack, never in Agora's kernel.

## State ownership

Agora owns actor authority, approvals, plan and deployment evidence references, Tool Runs, and local
Markdown history. The provider owns remote infrastructure and state. A successful apply does not
automatically satisfy work criteria or lifecycle gates; attach the captured plan and deployment as
artifacts or evidence when the active Method Pack requires them.

Run the executable plan-and-apply example:

```bash
uv run python samples/cloud-infrastructure/run.py
```

Run the native Terraform command preparation example:

```bash
uv run python samples/terraform-cli/run.py
```
