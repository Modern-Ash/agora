---
schema: "agora/tool-policy/v1"
default: "deny-unregistered"
---

# Tool policy

Tools include local commands and external systems such as repositories, Jira, CI/CD, Confluence,
cloud providers, observability platforms, and communication services.

## Rules

- Authentication remains in the environment, keychain, or external secret manager.
- Agora stores integration references, never raw credentials.
- Read and write capabilities are granted separately.
- Destructive, merge, release, and production actions require explicit policy and evidence.
- Method Packs and role policies may further restrict this catalog.
- Invoke installed operations through `agora tool invoke` so attribution and results remain durable.
- Create commits through `repository/commit`; its message must satisfy the configured Conventional
  Commits input rule.

## Project tools

| Tool | Capabilities | Authentication reference | Approval |
| --- | --- | --- | --- |
| repository | `repository.read`, `repository.write` | local Git configuration | operation policy |
| work-management | `issue.read`, `issue.write`, `issue.transition` | external CLI profile | role capability |
| ci-cd | `ci.read`, `ci.run`, `ci.cancel`, `deployment.create` | external CI/CD CLI profile | role capability and operation policy |
| knowledge-base | `docs.read`, `docs.write`, `docs.publish`, `docs.archive` | external documentation CLI profile | role capability and operation policy |

Installed Tool Packs live in subdirectories of `.agora/tools`. Presence in this catalog does not
grant authority; active Method Pack roles must list each allowed tool capability.
