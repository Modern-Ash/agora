---
schema: "agora/tool/v1"
id: "gitlab-issues"
name: "GitLab Issues CLI adapter"
version: "1.0.0"
dependencies: []
category: "issue-tracker"
executable: "glab"
version-command: ["version"]
minimum-runtime-version: "1.109.0"
authentication-reference: "gitlab-cli-profile-or-environment"
credential-sources: ["cli-session", "env"]
provider: "gitlab"
transport: "cli"
implements: "work-management"
implements-operations: ["search","view","comment","transition"]
---

# GitLab Issues CLI adapter

Maps the exact GitLab issue read, comment, and lifecycle subset of Agora's provider-neutral
work-management contract to `glab`. Repository and authentication selection remain in GitLab CLI;
full issue URLs may target another project.

Create is deliberately absent because the native command does not accept Agora's required neutral
work-item `type` input.
