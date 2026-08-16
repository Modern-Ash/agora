---
schema: "agora/tool-operation/v1"
id: "search"
name: "Search Jira work items"
capability: "issue.read"
risk: "read"
arguments: ["jira","workitem","search","--jql","{query}","--limit","50","--fields","key,issuetype,summary,status,assignee,priority","--json"]
inputs: ["query"]
result-kind: "work-item-list"
---

# Search Jira work items

Returns at most fifty work items for one explicit JQL query with a bounded field selection.
