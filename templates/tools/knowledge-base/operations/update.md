---
schema: "agora/tool-operation/v1"
id: "update"
name: "Update a document"
capability: "docs.write"
risk: "write"
arguments: ["page","update","{document}","--title","{title}","--body","{body}","--output","json"]
inputs: ["document","title","body"]
result-kind: "documentation"
---

# Update a document

Replaces the reviewed title and body of one external document.
