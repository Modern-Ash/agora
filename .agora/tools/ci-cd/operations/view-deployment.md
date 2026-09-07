---
schema: "agora/tool-operation/v1"
id: "view-deployment"
name: "View a deployment"
capability: "ci.read"
risk: "read"
arguments: ["deployment","view","{deployment}","--output","json"]
inputs: ["deployment"]
result-kind: "deployment"
---

# View a deployment

Returns external deployment status without changing it.
