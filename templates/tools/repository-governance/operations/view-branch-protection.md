---
schema: "agora/tool-operation/v1"
id: "view-branch-protection"
name: "View branch protection"
capability: "repository.governance.read"
risk: "read"
arguments: ["branch-protection","view","--project","{project}","--branch","{branch}","--output","json"]
inputs: ["project","branch"]
result-kind: "branch-protection"
---

# View branch protection

Returns the effective classic branch-protection configuration for one exact branch.
