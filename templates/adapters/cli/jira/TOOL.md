---
schema: "agora/tool/v1"
id: "jira"
name: "Jira Cloud ACLI adapter"
version: "1.0.0"
dependencies: []
category: "issue-tracker"
executable: "acli"
authentication-reference: "atlassian-cli-jira-site"
provider: "atlassian"
transport: "cli"
implements: "work-management"
---

# Jira Cloud ACLI adapter

Translates Agora's provider-neutral work-management contract into structured Atlassian CLI
commands. Authentication and active Jira site selection remain in ACLI.

All operations are non-interactive and request JSON where ACLI supports it. Installing this adapter
does not install ACLI or grant Jira authority.
