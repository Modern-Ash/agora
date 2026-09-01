---
schema: "agora/tool-operation/v1"
id: "list-code-alerts"
name: "List code scanning alerts"
capability: "security.read"
risk: "read"
arguments: ["code","list","--project","{project}","--limit","50","--output","json"]
inputs: ["project"]
result-kind: "security-alert-list"
---

# List code scanning alerts

Returns at most fifty code scanning alerts.
