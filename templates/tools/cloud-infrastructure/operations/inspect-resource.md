---
schema: "agora/tool-operation/v1"
id: "inspect-resource"
name: "Inspect a cloud resource"
capability: "cloud.read"
risk: "read"
environment-required: true
arguments: ["resource","inspect","{resource}","--environment","{environment}","--output","json"]
inputs: ["resource","environment"]
result-kind: "cloud-resource"
---

# Inspect a cloud resource

Returns reviewed metadata for one resource without changing it.
