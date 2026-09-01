---
schema: "agora/tool-operation/v1"
id: "trigger"
name: "Trigger a pipeline"
capability: "ci.run"
risk: "write"
arguments: ["pipeline","trigger","{pipeline}","--ref","{ref}","--parameters","{parameters}","--output","json"]
inputs: ["pipeline","ref","parameters"]
result-kind: "pipeline-run"
---

# Trigger a pipeline

Starts one pipeline with an explicit source reference and provider-adapter parameter string.
