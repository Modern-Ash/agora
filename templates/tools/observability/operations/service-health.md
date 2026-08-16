---
schema: "agora/tool-operation/v1"
id: "service-health"
name: "Inspect service health"
capability: "observability.read"
risk: "read"
environment-required: true
arguments: ["service","health","{service}","--environment","{environment}","--output","json"]
inputs: ["service","environment"]
result-kind: "service-health"
---

# Inspect service health

Returns current health for one service and environment.
