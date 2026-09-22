---
schema: "agora/tool-operation/v1"
id: "search"
name: "Search GitHub issues"
capability: "issue.read"
risk: "read"
arguments: ["search","issues","{query}","--repo","{project}","--state","{state}","--limit","50","--json","number,title,state,url,repository,updatedAt"]
inputs: ["query","project","state"]
input-values: {"state":["open","closed"]}
result-kind: "work-item-list"
---

# Search GitHub issues

Returns up to fifty issues from the explicitly selected repository and lifecycle state. The free-form `query`
remains one bounded GitHub search token/phrase; repository and state are passed through native CLI
flags instead of being embedded into that value.
