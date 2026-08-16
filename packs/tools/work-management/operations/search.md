---
schema: "agora/tool-operation/v1"
id: "search"
name: "Search work items"
capability: "issue.read"
risk: "read"
arguments: ["issue","search","--query","{query}","--output","json"]
inputs: ["query"]
result-kind: "work-item-list"
---

# Search work items

Returns work items that match a provider-neutral query interpreted by the configured wrapper.
