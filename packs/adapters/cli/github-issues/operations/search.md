---
schema: "agora/tool-operation/v1"
id: "search"
name: "Search GitHub issues"
capability: "issue.read"
risk: "read"
arguments: ["search","issues","{query}","--limit","50","--json","number,title,state,url,repository,updatedAt"]
inputs: ["query"]
result-kind: "work-item-list"
---

# Search GitHub issues

Returns up to fifty issues matching a bounded GitHub search query as JSON.
