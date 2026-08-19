---
schema: "agora/tool/v1"
id: "gitlab-merge-requests"
name: "GitLab Merge Requests CLI adapter"
version: "1.0.0"
dependencies: []
category: "code-review"
executable: "glab"
version-command: ["version"]
minimum-runtime-version: "1.109.0"
authentication-reference: "gitlab-cli-profile-or-environment"
credential-sources: ["cli-session", "env"]
provider: "gitlab"
transport: "cli"
implements: "code-review"
implements-operations: ["view","create","comment","checks"]
---

# GitLab Merge Requests CLI adapter

Maps the exact GitLab merge-request inspection, creation, comment, and head-pipeline subset of
Agora's provider-neutral code-review contract to `glab`. Repository and authentication selection
remain in GitLab CLI; a full merge-request URL may target another project for supported reads.

List, approval, request-changes, and merge are deliberately absent. Native list and merge strategies
need conditional flag translation, approval cannot preserve Agora's required decision body, and
GitLab CLI has no equivalent request-changes decision.
