---
schema: "agora/tool-operation/v1"
id: "list-secret-alerts"
name: "List redacted GitHub secret scanning alerts"
capability: "security.read"
risk: "read"
arguments: ["api","--method","GET","repos/{project}/secret-scanning/alerts","--raw-field","per_page=50","--jq","[.[] | {number,state,secret_type,secret_type_display_name,resolution,resolved_at,created_at,updated_at,html_url,publicly_leaked,multi_repo,push_protection_bypassed,push_protection_bypassed_at}]"]
inputs: ["project"]
result-kind: "security-alert-list"
---

# List redacted GitHub secret scanning alerts

Selects metadata explicitly and excludes the provider response's `secret` value and locations.
