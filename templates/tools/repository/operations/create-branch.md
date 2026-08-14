---
schema: "agora/tool-operation/v1"
id: "create-branch"
name: "Create a branch"
capability: "repository.write"
risk: "write"
arguments: ["checkout","-b","{branch}"]
inputs: ["branch"]
result-kind: "repository-change"
---

# Create a branch

Creates and checks out a caller-selected branch. Project and Method Pack policy still apply.
