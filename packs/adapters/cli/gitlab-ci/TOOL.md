---
schema: "agora/tool/v1"
id: "gitlab-ci"
name: "GitLab CI/CD CLI adapter"
version: "1.0.0"
dependencies: []
category: "ci"
executable: "glab"
version-command: ["version"]
minimum-runtime-version: "1.109.0"
authentication-reference: "gitlab-cli-profile-or-environment"
credential-sources: ["cli-session", "env"]
provider: "gitlab"
transport: "cli"
implements: "ci-cd"
implements-operations: ["list-runs","view-run","cancel-run"]
---

# GitLab CI/CD CLI adapter

Maps the exact GitLab pipeline list, inspection, and cancellation subset of Agora's provider-neutral
CI/CD contract to `glab`. Project and authentication selection remain in GitLab CLI.

Trigger is deliberately absent because the native command cannot preserve Agora's required neutral
pipeline identity together with ref and parameters. Deployment operations are absent because GitLab
CLI does not expose an equivalent bounded native contract.
