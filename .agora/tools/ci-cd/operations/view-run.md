---
schema: "agora/tool-operation/v1"
id: "view-run"
name: "View a pipeline run"
capability: "ci.read"
risk: "read"
arguments: ["run","view","{run}","--output","json"]
inputs: ["run"]
result-kind: "pipeline-run"
---

# View a pipeline run

Returns status and evidence for one external pipeline run.
