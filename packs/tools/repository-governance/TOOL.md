---
schema: "agora/tool/v1"
id: "repository-governance"
name: "Repository governance"
version: "1.0.0"
dependencies: []
category: "repository-governance"
executable: "repo-policyctl"
authentication-reference: "team-repository-governance-profile"
timeout-seconds: 300
max-output-bytes: 1048576
---

# Repository governance

Provides a provider-neutral read contract for repository policy, rulesets, branch protection, and
policy files. Policy mutation belongs in a reviewed adapter that validates a neutral policy artifact.
