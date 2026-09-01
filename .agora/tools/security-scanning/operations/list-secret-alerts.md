---
schema: "agora/tool-operation/v1"
id: "list-secret-alerts"
name: "List redacted secret scanning alerts"
capability: "security.read"
risk: "read"
arguments: ["secret","list","--project","{project}","--limit","50","--redact-secrets","--output","json"]
inputs: ["project"]
result-kind: "security-alert-list"
---

# List redacted secret scanning alerts

Returns at most fifty secret alert metadata records. Implementations must never return secret values.
