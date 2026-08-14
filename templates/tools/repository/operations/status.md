---
schema: "agora/tool-operation/v1"
id: "status"
name: "Inspect repository status"
capability: "repository.read"
risk: "read"
arguments: ["status","--short"]
inputs: []
result-kind: "repository-status"
---

# Inspect repository status

Reads the concise working-tree status without changing repository state.
