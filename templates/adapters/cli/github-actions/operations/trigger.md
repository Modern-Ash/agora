---
schema: "agora/tool-operation/v1"
id: "trigger"
name: "Trigger a GitHub Actions workflow"
capability: "ci.run"
risk: "write"
arguments: ["workflow","run","{pipeline}","--ref","{ref}","--raw-field","{parameters}"]
inputs: ["pipeline","ref","parameters"]
result-kind: "pipeline-run"
---

# Trigger a GitHub Actions workflow

Creates a `workflow_dispatch` event with one reviewed `key=value` input. Additional inputs require a
reviewed adapter amendment rather than shell expansion.
