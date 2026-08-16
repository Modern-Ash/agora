---
schema: "agora/tool-operation/v1"
id: "view-policy-file"
name: "View a GitHub repository policy file"
capability: "repository.governance.read"
risk: "read"
arguments: ["api","--method","GET","repos/{project}/contents/{path}","--header","Accept: application/vnd.github.raw+json"]
inputs: ["project","path"]
result-kind: "repository-policy-file"
---

# View a GitHub repository policy file

Returns the raw contents of one exact policy path, including `.github/CODEOWNERS` when present.
