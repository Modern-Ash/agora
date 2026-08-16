---
schema: "agora/tool-operation/v1"
id: "list-items"
name: "List GitHub Project items"
capability: "portfolio.read"
risk: "read"
arguments: ["project","item-list","{project}","--owner","{owner}","--query","{query}","--limit","50","--format","json"]
inputs: ["owner","project","query"]
result-kind: "portfolio-item-list"
---

# List GitHub Project items

Returns at most fifty items matching a GitHub Projects query as JSON.
