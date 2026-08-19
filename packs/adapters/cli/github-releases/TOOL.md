---
schema: "agora/tool/v1"
id: "github-releases"
name: "GitHub Releases CLI adapter"
version: "1.0.0"
dependencies: []
category: "release"
executable: "gh"
version-command: ["--version"]
minimum-runtime-version: "2.82.1"
authentication-reference: "github-cli-profile"
credential-sources: ["cli-session", "env"]
provider: "github"
transport: "cli"
implements: "release-management"
---

# GitHub Releases CLI adapter

Maps bounded release reads, attestation verification, and publication from an existing remote tag
and explicit artifact to non-interactive GitHub CLI commands.
