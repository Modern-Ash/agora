---
schema: "agora/tool-operation/v1"
id: "list-releases"
name: "List releases"
capability: "release.read"
risk: "read"
arguments: ["release","list","--project","{project}","--limit","50","--output","json"]
inputs: ["project"]
result-kind: "release-list"
---

# List releases

Returns at most fifty recent releases.
