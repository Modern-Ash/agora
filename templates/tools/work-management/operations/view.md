---
schema: "agora/tool-operation/v1"
id: "view"
name: "View a work item"
capability: "issue.read"
risk: "read"
arguments: ["issue","view","{issue}","--output","json"]
inputs: ["issue"]
result-kind: "work-item"
---

# View a work item

Returns one externally managed work item without changing it.
