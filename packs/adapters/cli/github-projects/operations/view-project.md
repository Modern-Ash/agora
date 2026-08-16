---
schema: "agora/tool-operation/v1"
id: "view-project"
name: "View a GitHub Project"
capability: "portfolio.read"
risk: "read"
arguments: ["project","view","{project}","--owner","{owner}","--format","json"]
inputs: ["owner","project"]
result-kind: "portfolio-project"
---

# View a GitHub Project

Returns one GitHub Project as JSON.
