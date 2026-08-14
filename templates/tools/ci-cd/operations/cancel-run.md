---
schema: "agora/tool-operation/v1"
id: "cancel-run"
name: "Cancel a pipeline run"
capability: "ci.cancel"
risk: "destructive"
arguments: ["run","cancel","{run}","--output","json"]
inputs: ["run"]
result-kind: "pipeline-run"
---

# Cancel a pipeline run

Stops an external run. No bundled Method Pack role receives `ci.cancel` by default.
