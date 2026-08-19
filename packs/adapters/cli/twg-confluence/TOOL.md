---
schema: "agora/tool/v1"
id: "twg-confluence"
name: "Atlassian TWG Confluence CLI adapter"
version: "1.0.0"
dependencies: []
category: "documentation"
executable: "twg"
version-command: ["-v"]
minimum-runtime-version: "1.2.5"
authentication-reference: "twg-oauth-profile-or-environment"
credential-sources: ["cli-session"]
provider: "atlassian-confluence"
transport: "cli"
implements: "knowledge-base"
implements-operations: ["view","create","update","publish","archive"]
---

# Atlassian TWG Confluence CLI adapter

Implements the exact Confluence page lifecycle subset of Agora's knowledge-base contract through
Atlassian Teamwork Graph CLI. Authentication, site selection, OAuth permissions, and credentials
remain in `twg` or its environment.

Search is deliberately absent. TWG separates natural-text and CQL search, and neither surface can
bind Agora's independent `space` and `query` inputs without a reviewed escaping wrapper.
