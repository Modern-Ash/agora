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

## Project tools

| Tool       | Capabilities                       | Authentication reference | Approval       |
| ---------- | ---------------------------------- | ------------------------ | -------------- |
| repository | read, branch, commit, pull-request | local Git credentials    | project policy |
