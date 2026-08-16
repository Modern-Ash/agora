---
schema: "agora/tool-operation/v1"
id: "search"
name: "Search GitLab issues"
capability: "issue.read"
risk: "read"
arguments: ["issue","list","--search","{query}","--all","--per-page","50","--output","json"]
inputs: ["query"]
result-kind: "work-item-list"
---

# Search GitLab issues

Returns at most fifty open or closed issues from the selected GitLab project as JSON.
