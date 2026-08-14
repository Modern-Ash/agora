---
schema: "agora/tool/v1"
id: "github-issues"
name: "GitHub Issues CLI adapter"
version: "1.0.0"
dependencies: []
category: "issue-tracker"
executable: "gh"
authentication-reference: "github-cli-profile"
provider: "github"
transport: "cli"
implements: "work-management"
---

# GitHub Issues CLI adapter

Translates Agora's provider-neutral work-management capabilities into structured GitHub CLI
commands. Repository selection and authentication remain in `gh`; explicit issue URLs may be used
when an operation targets another repository.
