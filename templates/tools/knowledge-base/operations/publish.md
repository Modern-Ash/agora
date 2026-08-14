---
schema: "agora/tool-operation/v1"
id: "publish"
name: "Publish a document"
capability: "docs.publish"
risk: "write"
arguments: ["page","publish","{document}","--output","json"]
inputs: ["document"]
result-kind: "documentation-publication"
---

# Publish a document

Publishes one external document. No bundled Method Pack role receives `docs.publish` by default.
