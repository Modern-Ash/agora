---
schema: "agora/tool-operation/v1"
id: "view-policy-file"
name: "View a repository policy file"
capability: "repository.governance.read"
risk: "read"
arguments: ["policy-file","view","--project","{project}","--path","{path}"]
inputs: ["project","path"]
result-kind: "repository-policy-file"
---

# View a repository policy file

Returns one exact repository policy file, such as `.github/CODEOWNERS`, without changing it.
