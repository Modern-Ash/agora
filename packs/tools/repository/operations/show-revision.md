---
schema: "agora/tool-operation/v1"
id: "show-revision"
name: "Inspect a revision"
capability: "repository.read"
risk: "read"
arguments: ["show","--stat","--oneline","{revision}"]
inputs: ["revision"]
result-kind: "repository-revision"
---

# Inspect a revision

Returns the summary and file statistics for a caller-selected revision.
