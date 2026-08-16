---
schema: "agora/tool-operation/v1"
id: "create"
name: "Create a document"
capability: "docs.write"
risk: "write"
arguments: ["page","create","--space","{space}","--parent","{parent}","--title","{title}","--body","{body}","--output","json"]
inputs: ["space","parent","title","body"]
result-kind: "documentation"
---

# Create a document

Creates one external draft document with attributable durable inputs.
