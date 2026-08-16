---
schema: "agora/tool-operation/v1"
id: "list-projects"
name: "List GitHub Projects"
capability: "portfolio.read"
risk: "read"
arguments: ["project","list","--owner","{owner}","--closed","--limit","50","--format","json"]
inputs: ["owner"]
result-kind: "portfolio-project-list"
---

# List GitHub Projects

Returns at most fifty open and closed projects as JSON.
