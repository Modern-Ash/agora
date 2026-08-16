---
schema: "agora/tool-operation/v1"
id: "cancel-run"
name: "Cancel a GitLab pipeline run"
capability: "ci.cancel"
risk: "destructive"
arguments: ["ci","cancel","pipeline","{run}"]
inputs: ["run"]
result-kind: "pipeline-run"
---

# Cancel a GitLab pipeline run

Requests cancellation of one pipeline run. Bundled roles do not receive `ci.cancel` authority.
