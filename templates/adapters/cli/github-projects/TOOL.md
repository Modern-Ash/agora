---
schema: "agora/tool/v1"
id: "github-projects"
name: "GitHub Projects CLI adapter"
version: "1.0.0"
dependencies: []
category: "portfolio"
executable: "gh"
version-command: ["--version"]
minimum-runtime-version: "2.82.1"
authentication-reference: "github-cli-project-profile"
provider: "github"
transport: "cli"
implements: "portfolio-management"
---

# GitHub Projects CLI adapter

Maps portfolio projects and item references to non-interactive GitHub Projects CLI commands. The
external `gh` profile must carry the project scope; Agora never refreshes authentication itself.
