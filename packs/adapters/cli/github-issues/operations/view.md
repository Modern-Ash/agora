---
schema: "agora/tool-operation/v1"
id: "view"
name: "View a GitHub issue"
capability: "issue.read"
risk: "read"
arguments: ["issue","view","{issue}","--json","number,title,body,state,stateReason,labels,assignees,milestone,url,createdAt,updatedAt"]
inputs: ["issue"]
result-kind: "work-item"
---

# View a GitHub issue

Returns one issue as JSON without comments or reaction details.
