---
schema: "agora/tool-operation/v1"
id: "list-rulesets"
name: "List repository rulesets"
capability: "repository.governance.read"
risk: "read"
arguments: ["ruleset","list","--project","{project}","--limit","50","--output","json"]
inputs: ["project"]
result-kind: "repository-ruleset-list"
---

# List repository rulesets

Returns at most fifty repository rulesets.
