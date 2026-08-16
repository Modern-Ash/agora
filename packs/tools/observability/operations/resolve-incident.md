---
schema: "agora/tool-operation/v1"
id: "resolve-incident"
name: "Resolve an incident"
capability: "incident.resolve"
risk: "write"
arguments: ["incident","resolve","{incident}","--resolution","{resolution}","--output","json"]
inputs: ["incident","resolution"]
result-kind: "incident-resolution"
---

# Resolve an incident

Resolves an external incident. No bundled Method Pack role receives `incident.resolve` by default.
