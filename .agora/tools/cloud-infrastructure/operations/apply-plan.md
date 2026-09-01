---
schema: "agora/tool-operation/v1"
id: "apply-plan"
name: "Apply an infrastructure plan"
capability: "cloud.deploy"
risk: "write"
environment-required: true
arguments: ["change","apply","{plan}","--environment","{environment}","--output","json"]
inputs: ["plan","environment"]
result-kind: "cloud-deployment"
---

# Apply an infrastructure plan

Applies one previously reviewed plan. No bundled Method Pack role receives `cloud.deploy` by default.
