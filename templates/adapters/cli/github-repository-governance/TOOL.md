---
schema: "agora/tool/v1"
id: "github-repository-governance"
name: "GitHub repository governance CLI adapter"
version: "1.0.0"
dependencies: []
category: "repository-governance"
executable: "gh"
version-command: ["--version"]
minimum-runtime-version: "2.82.1"
authentication-reference: "github-cli-profile"
provider: "github"
transport: "cli"
implements: "repository-governance"
---

# GitHub repository governance CLI adapter

Maps repository metadata, rulesets, classic branch protection, and exact policy-file reads to
bounded non-interactive GitHub CLI commands. Administration remains outside this read-only adapter.
