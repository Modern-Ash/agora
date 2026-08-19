---
schema: "agora/tool/v1"
id: "github-actions"
name: "GitHub Actions CLI adapter"
version: "1.0.0"
dependencies: []
category: "ci"
executable: "gh"
version-command: ["--version"]
minimum-runtime-version: "2.45.0"
authentication-reference: "github-cli-profile"
credential-sources: ["cli-session", "env"]
provider: "github"
transport: "cli"
implements: "ci-cd"
---

# GitHub Actions CLI adapter

Translates Agora's provider-neutral CI/CD capabilities into structured GitHub CLI commands. It uses
the repository and authentication already selected by `gh`; Agora never reads or persists GitHub
credentials.

This adapter is installed explicitly. Discovering `gh` on `PATH` does not grant capabilities or
replace the provider-neutral `ci-cd` Tool Pack.
