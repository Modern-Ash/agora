---
schema: "agora/tool-operation/v1"
id: "commit"
name: "Create a Conventional Commit"
capability: "repository.write"
risk: "write"
arguments: ["commit","-m","{message}"]
inputs: ["message"]
input-rules: {"message":"conventional-commits/v1.0.0"}
result-kind: "repository-change"
---

# Create a Conventional Commit

Creates a Git commit from already staged changes. Agora validates the complete message against the
Conventional Commits 1.0.0 structure before preparing or launching Git. Staging remains an explicit
repository action outside this operation.
