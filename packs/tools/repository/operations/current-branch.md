---
schema: "agora/tool-operation/v1"
id: "current-branch"
name: "Inspect current branch"
capability: "repository.read"
risk: "read"
arguments: ["branch","--show-current"]
inputs: []
result-kind: "repository-branch"
---

# Inspect current branch

Returns the active Git branch.
