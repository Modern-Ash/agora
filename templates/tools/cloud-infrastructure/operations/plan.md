---
schema: "agora/tool-operation/v1"
id: "plan"
name: "Plan an infrastructure change"
capability: "cloud.plan"
risk: "read"
environment-required: true
arguments: ["change","plan","--environment","{environment}","--change","{change}","--output","json"]
inputs: ["environment","change"]
result-kind: "infrastructure-plan"
---

# Plan an infrastructure change

Produces a non-mutating plan for one durable change description.
