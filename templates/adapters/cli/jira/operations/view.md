---
schema: "agora/tool-operation/v1"
id: "view"
name: "View a Jira work item"
capability: "issue.read"
risk: "read"
arguments: ["jira","workitem","view","{issue}","--fields","key,issuetype,summary,status,assignee,description","--json"]
inputs: ["issue"]
result-kind: "work-item"
---

# View a Jira work item

Returns one work item with a bounded field selection as JSON.
