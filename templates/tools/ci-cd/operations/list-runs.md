---
schema: "agora/tool-operation/v1"
id: "list-runs"
name: "List pipeline runs"
capability: "ci.read"
risk: "read"
arguments: ["run","list","--pipeline","{pipeline}","--output","json"]
inputs: ["pipeline"]
result-kind: "pipeline-run-list"
---

# List pipeline runs

Returns recent runs for one provider-neutral pipeline identity.
