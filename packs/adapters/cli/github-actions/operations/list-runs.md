---
schema: "agora/tool-operation/v1"
id: "list-runs"
name: "List GitHub Actions runs"
capability: "ci.read"
risk: "read"
arguments: ["run","list","--workflow","{pipeline}","--limit","50","--json","databaseId,displayTitle,event,headBranch,headSha,status,conclusion,url,workflowName"]
inputs: ["pipeline"]
result-kind: "pipeline-run-list"
---

# List GitHub Actions runs

Returns up to fifty recent runs for one workflow as JSON.
