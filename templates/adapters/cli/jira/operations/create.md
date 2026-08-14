---
schema: "agora/tool-operation/v1"
id: "create"
name: "Create a Jira work item"
capability: "issue.write"
risk: "write"
arguments: ["jira","workitem","create","--project","{project}","--type","{type}","--summary","{title}","--description","{description}","--json"]
inputs: ["project","type","title","description"]
result-kind: "work-item"
---

# Create a Jira work item

Creates one work item non-interactively and returns JSON.
