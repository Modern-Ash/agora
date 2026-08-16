---
schema: "agora/tool-operation/v1"
id: "list-dependency-alerts"
name: "List GitHub Dependabot alerts"
capability: "security.read"
risk: "read"
arguments: ["api","--method","GET","repos/{project}/dependabot/alerts","--raw-field","per_page=50","--jq","[.[] | {number,state,dependency,security_advisory:{ghsa_id:.security_advisory.ghsa_id,cve_id:.security_advisory.cve_id,summary:.security_advisory.summary,severity:.security_advisory.severity},security_vulnerability,created_at,updated_at,dismissed_at,dismissed_reason,fixed_at,html_url}]"]
inputs: ["project"]
result-kind: "security-alert-list"
---

# List GitHub Dependabot alerts

Returns selected vulnerability and dependency fields for at most fifty alerts.
