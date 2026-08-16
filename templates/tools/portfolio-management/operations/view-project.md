---
schema: "agora/tool-operation/v1"
id: "view-project"
name: "View a portfolio project"
capability: "portfolio.read"
risk: "read"
arguments: ["project","view","--owner","{owner}","--project","{project}","--output","json"]
inputs: ["owner","project"]
result-kind: "portfolio-project"
---

# View a portfolio project

Returns one portfolio project.
