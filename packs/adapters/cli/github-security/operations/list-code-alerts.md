---
schema: "agora/tool-operation/v1"
id: "list-code-alerts"
name: "List GitHub code scanning alerts"
capability: "security.read"
risk: "read"
arguments: ["api","--method","GET","repos/{project}/code-scanning/alerts","--raw-field","per_page=50","--jq","[.[] | {number,state,rule,tool,most_recent_instance,created_at,updated_at,dismissed_at,dismissed_reason,html_url}]"]
inputs: ["project"]
result-kind: "security-alert-list"
---

# List GitHub code scanning alerts

Returns selected fields for at most fifty code scanning alerts.
