---
schema: "agora/tool-operation/v1"
id: "comment"
name: "Comment on a work item"
capability: "issue.write"
risk: "write"
arguments: ["issue","comment","{issue}","--body","{body}","--output","json"]
inputs: ["issue","body"]
result-kind: "work-item-comment"
---

# Comment on a work item

Adds durable external context without treating the external system as Agora's source of truth.
