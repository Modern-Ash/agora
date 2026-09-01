---
schema: "agora/tool-operation/v1"
id: "view-ruleset"
name: "View a repository ruleset"
capability: "repository.governance.read"
risk: "read"
arguments: ["ruleset","view","--project","{project}","--ruleset","{ruleset}","--output","json"]
inputs: ["project","ruleset"]
result-kind: "repository-ruleset"
---

# View a repository ruleset

Returns one repository ruleset including its conditions and enforcement state.
