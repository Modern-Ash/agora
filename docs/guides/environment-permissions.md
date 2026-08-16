# Environment permissions

Agora environment policies restrict governed Tool Runs for project-defined targets without
hard-coding `development`, `staging`, `production`, a cloud vendor, or an account model into the
kernel. A project can name environments after deployment tiers, tenants, regions, laboratories, or
any other stable governance boundary.

Policies are Markdown under `.agora/environments/<environment-id>.md`. They are versioned with the
repository and evaluated together with Method Pack roles and Tool Pack operations.

## Create a policy

Create a production policy that admits deployment creation only after Product Owner approval and
successful work evidence:

```bash
agora environment add \
  --id production \
  --name "Production" \
  --capability deployment.create \
  --required-approval-role product-owner \
  --require-successful-evidence
```

The resulting contract remains readable without the CLI:

```markdown
---
schema: "agora/environment-policy/v1"
id: "production"
name: "Production"
allowed-tool-capabilities: ["deployment.create"]
required-approval-roles: ["product-owner"]
require-successful-evidence: true
---

# Production
```

Use repeated `--capability` and `--required-approval-role` options when a policy admits more than
one value. Every policy must allow at least one provider-neutral Tool Pack capability.

Inspect the project policies with:

```bash
agora environment list
agora environment show --id production
```

## Restrict roles

Method Pack roles declare the environments in which their tool capabilities may operate:

```markdown
allowed-tool-capabilities: ["ci.read", "ci.run", "deployment.create"]
allowed-environments: ["integration", "staging"]
```

`["*"]` permits that role's existing capabilities in any environment admitted by project policy.
The wildcard does not grant a capability: the role and environment policy must both contain it.
Agora requires one assigned role to grant both the exact capability and the selected environment;
permissions from separate roles are not combined.

Bundled Spec-Driven, Scrum, and Kanban examples use `["*"]` so projects can introduce their own
environment names without editing the example Method Packs first. Replace the wildcard on a
reviewable branch when a role must be limited.

## Require an environment

A Tool Pack operation opts into mandatory environment governance with:

```markdown
environment-required: true
```

Bundled cloud operations, deployment creation, environment-scoped observability health checks, and
their reviewed CLI adapters use this flag. An invocation without a governed environment is rejected
before `RUN.md` is written.

Invoke an operation with the stable governance id:

```bash
agora tool invoke \
  --id deploy-release \
  --tool ci-cd \
  --operation create-deployment \
  --actor delivery-agent \
  --swarm payments \
  --work release \
  --environment production \
  --input environment=provider-production \
  --input artifact=sha256:verified
```

`--environment production` selects Agora policy. The `environment` Tool Pack input in this example
is provider data translated by the reviewed adapter. The values may match, but Agora does not assume
they do. This separation keeps accounts, project ids, regions, Terraform directories, and provider
naming outside the kernel.

## Enforcement sequence

Before preparing a Tool Run, Agora requires:

1. an active actor assignment in a ready or running swarm;
2. an assigned role that grants the operation capability;
3. the environment policy to admit that capability;
4. the same granting role to admit the environment id;
5. linked work when the policy requires approval or evidence;
6. every environment approval role on that work;
7. at least one successful evidence record when required; and
8. any additional operation-level approval.

Agora repeats these checks immediately before launch. A prepared run therefore cannot retain
authority after its role, environment policy, work approval, evidence, or Tool Pack operation has
changed. For authenticated actors, `environment` is part of the canonical Tool Run authorization
payload, so a signature for one environment cannot authorize another.

`RUN.md` persists the environment id. A launched process receives `AGORA_ENVIRONMENT` in addition to
the existing Agora context variables. Credentials remain in the external CLI profile, workload
identity, keychain, or secret manager and must never appear in an environment policy.

## Customize safely

Treat changes under `.agora/environments/`, role `allowed-environments`, and operation
`environment-required` as policy changes. Review them in Git with the affected Method and Tool Pack
composition. After a local Method or Tool Pack amendment, refresh the deterministic composition
lock:

```bash
agora pack lock --scope project
agora validate
```

Validation rejects malformed policies, filename/id mismatches, role references to missing project
environments, Tool Runs that reference missing environments, and prepared runs that no longer meet
current environment policy.

Environment policies govern Agora Tool Runs; they do not create an operating-system sandbox or
replace provider IAM. External runners and provider controls must still bound filesystem, network,
syscall, resource, tenant, account, and credential access.

Run the [environment permissions sample](../../samples/environment-permissions/README.md) to see
approval and evidence failures followed by a successful preparation without launching a provider.
