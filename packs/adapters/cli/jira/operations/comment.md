---
schema: "agora/tool-operation/v1"
id: "comment"
name: "Comment on a Jira work item"
capability: "issue.write"
risk: "write"
arguments: ["jira","workitem","comment","create","--key","{issue}","--body","{body}","--json"]
inputs: ["issue","body"]
result-kind: "work-item-comment"
---

# Comment on a Jira work item

Adds one comment using the project's default visibility and returns JSON.
