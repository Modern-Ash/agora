---
schema: "agora/tool-operation/v1"
id: "inspect-repository"
name: "Inspect repository governance"
capability: "repository.governance.read"
risk: "read"
arguments: ["repository","inspect","--project","{project}","--output","json"]
inputs: ["project"]
result-kind: "repository-governance"
---

# Inspect repository governance

Returns repository-wide merge and governance configuration.
