---
schema: "agora/tool-operation/v1"
id: "cancel-run"
name: "Cancel a GitHub Actions run"
capability: "ci.cancel"
risk: "destructive"
arguments: ["run","cancel","{run}"]
inputs: ["run"]
result-kind: "pipeline-run"
---

# Cancel a GitHub Actions run

Requests cancellation of one workflow run. Bundled roles do not receive `ci.cancel` authority.
