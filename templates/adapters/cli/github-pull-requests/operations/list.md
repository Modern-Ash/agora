---
schema: "agora/tool-operation/v1"
id: "list"
name: "List GitHub pull requests"
capability: "review.read"
risk: "read"
arguments: ["pr","list","--repo","{project}","--state","{state}","--limit","50","--json","number,title,state,isDraft,headRefName,baseRefName,url,updatedAt"]
inputs: ["project","state"]
input-values: {"state":["open","closed","merged","all"]}
result-kind: "code-review-list"
---

# List GitHub pull requests

Returns at most fifty pull requests as JSON.
