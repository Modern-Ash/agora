---
schema: "agora/tool-operation/v1"
id: "view"
name: "View a document"
capability: "docs.read"
risk: "read"
arguments: ["page","view","{document}","--output","json"]
inputs: ["document"]
result-kind: "documentation"
---

# View a document

Returns one external document without changing it.
