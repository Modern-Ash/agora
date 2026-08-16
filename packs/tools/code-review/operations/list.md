---
schema: "agora/tool-operation/v1"
id: "list"
name: "List code reviews"
capability: "review.read"
risk: "read"
arguments: ["list","--project","{project}","--state","{state}","--limit","50"]
inputs: ["project","state"]
input-values: {"state":["open","closed","merged","all"]}
result-kind: "code-review-list"
---

# List code reviews

Returns at most fifty change requests in the selected provider-neutral state.
