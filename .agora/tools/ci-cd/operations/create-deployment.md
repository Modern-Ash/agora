---
schema: "agora/tool-operation/v1"
id: "create-deployment"
name: "Create a deployment"
capability: "deployment.create"
risk: "write"
environment-required: true
arguments: ["deployment","create","--environment","{environment}","--artifact","{artifact}","--output","json"]
inputs: ["environment","artifact"]
result-kind: "deployment"
---

# Create a deployment

Creates an external deployment from an immutable artifact identity. No bundled Method Pack role
receives `deployment.create` by default; teams must grant it and define approval policy explicitly.
