---
schema: "agora/tool-operation/v1"
id: "view-branch-protection"
name: "View GitHub branch protection"
capability: "repository.governance.read"
risk: "read"
arguments: ["api","--method","GET","repos/{project}/branches/{branch}/protection"]
inputs: ["project","branch"]
result-kind: "branch-protection"
---

# View GitHub branch protection

Returns classic branch protection for one exact branch. Ruleset evaluation remains a separate read.
