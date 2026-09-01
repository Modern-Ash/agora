---
schema: "agora/tool/v1"
id: "code-review"
name: "Code review"
version: "1.0.0"
dependencies: []
category: "code-review"
executable: "reviewctl"
authentication-reference: "team-code-review-profile"
timeout-seconds: 300
max-output-bytes: 1048576
---

# Code review

Provides a provider-neutral contract for change requests, review decisions, checks, and merge.
Provider authentication and repository selection remain outside Agora.
