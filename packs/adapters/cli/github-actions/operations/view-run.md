---
schema: "agora/tool-operation/v1"
id: "view-run"
name: "View a GitHub Actions run"
capability: "ci.read"
risk: "read"
arguments: ["run","view","{run}","--json","attempt,conclusion,createdAt,databaseId,displayTitle,event,headBranch,headSha,jobs,status,updatedAt,url,workflowName"]
inputs: ["run"]
result-kind: "pipeline-run"
---

# View a GitHub Actions run

Returns one workflow run and its jobs as JSON without downloading logs.
