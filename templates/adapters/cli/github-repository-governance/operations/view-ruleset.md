---
schema: "agora/tool-operation/v1"
id: "view-ruleset"
name: "View a GitHub repository ruleset"
capability: "repository.governance.read"
risk: "read"
arguments: ["api","--method","GET","repos/{project}/rulesets/{ruleset}"]
inputs: ["project","ruleset"]
result-kind: "repository-ruleset"
---

# View a GitHub repository ruleset

Returns one repository ruleset including conditions, rules, bypass actors, and enforcement state.
