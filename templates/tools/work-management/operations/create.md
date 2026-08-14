---
schema: "agora/tool-operation/v1"
id: "create"
name: "Create a work item"
capability: "issue.write"
risk: "write"
arguments: ["issue","create","--project","{project}","--type","{type}","--title","{title}","--description","{description}","--output","json"]
inputs: ["project","type","title","description"]
result-kind: "work-item"
---

# Create a work item

Creates one external work item. Agora records the accountable actor and complete structured command.
