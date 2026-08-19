---
schema: "agora/tool/v1"
id: "github-pull-requests"
name: "GitHub Pull Requests CLI adapter"
version: "1.0.0"
dependencies: []
category: "code-review"
executable: "gh"
version-command: ["--version"]
minimum-runtime-version: "2.45.0"
authentication-reference: "github-cli-profile"
credential-sources: ["cli-session", "env"]
provider: "github"
transport: "cli"
implements: "code-review"
---

# GitHub Pull Requests CLI adapter

Translates the provider-neutral code-review contract into non-interactive GitHub CLI commands.
Authentication, host selection, and repository access remain in the developer's `gh` profile.
