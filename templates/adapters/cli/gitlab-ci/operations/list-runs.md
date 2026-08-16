---
schema: "agora/tool-operation/v1"
id: "list-runs"
name: "List GitLab pipeline runs"
capability: "ci.read"
risk: "read"
arguments: ["ci","list","--name","{pipeline}","--per-page","50","--output","json"]
inputs: ["pipeline"]
result-kind: "pipeline-run-list"
---

# List GitLab pipeline runs

Returns at most fifty recent runs for one GitLab pipeline name as JSON.
