---
schema: "agora/tool-operation/v1"
id: "list-rulesets"
name: "List GitHub repository rulesets"
capability: "repository.governance.read"
risk: "read"
arguments: ["api","--method","GET","repos/{project}/rulesets","--raw-field","per_page=50"]
inputs: ["project"]
result-kind: "repository-ruleset-list"
---

# List GitHub repository rulesets

Returns at most fifty repository rulesets through the authenticated GitHub API.
