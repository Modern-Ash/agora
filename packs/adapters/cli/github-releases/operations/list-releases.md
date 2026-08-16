---
schema: "agora/tool-operation/v1"
id: "list-releases"
name: "List GitHub releases"
capability: "release.read"
risk: "read"
arguments: ["release","list","--repo","{project}","--limit","50","--json","createdAt,isDraft,isLatest,isPrerelease,name,publishedAt,tagName"]
inputs: ["project"]
result-kind: "release-list"
---

# List GitHub releases

Returns at most fifty releases as selected JSON fields.
