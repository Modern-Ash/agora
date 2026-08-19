---
schema: "agora/tool/v1"
id: "github-security"
name: "GitHub security scanning CLI adapter"
version: "1.0.0"
dependencies: []
category: "security"
executable: "gh"
version-command: ["--version"]
minimum-runtime-version: "2.82.1"
authentication-reference: "github-cli-security-profile"
credential-sources: ["cli-session", "env"]
provider: "github"
transport: "cli"
implements: "security-scanning"
---

# GitHub security scanning CLI adapter

Maps bounded code scanning, Dependabot, and secret scanning reads to GitHub API requests through
`gh`. Selected JSON fields keep results useful while secret values are removed before persistence.
