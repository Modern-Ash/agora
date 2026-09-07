---
schema: "agora/tool-operation/v1"
id: "list-items"
name: "List portfolio items"
capability: "portfolio.read"
risk: "read"
arguments: ["item","list","--owner","{owner}","--project","{project}","--query","{query}","--limit","50","--output","json"]
inputs: ["owner","project","query"]
result-kind: "portfolio-item-list"
---

# List portfolio items

Returns at most fifty items matching an explicit provider-adapter query.
