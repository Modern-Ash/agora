---
schema: "agora/tool-operation/v1"
id: "list-dependency-alerts"
name: "List dependency alerts"
capability: "security.read"
risk: "read"
arguments: ["dependency","list","--project","{project}","--limit","50","--output","json"]
inputs: ["project"]
result-kind: "security-alert-list"
---

# List dependency alerts

Returns at most fifty dependency vulnerability alerts.
