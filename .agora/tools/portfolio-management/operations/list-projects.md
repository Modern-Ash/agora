---
schema: "agora/tool-operation/v1"
id: "list-projects"
name: "List portfolio projects"
capability: "portfolio.read"
risk: "read"
arguments: ["project","list","--owner","{owner}","--limit","50","--output","json"]
inputs: ["owner"]
result-kind: "portfolio-project-list"
---

# List portfolio projects

Returns at most fifty open and closed projects for one owner.
