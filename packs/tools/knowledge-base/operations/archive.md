---
schema: "agora/tool-operation/v1"
id: "archive"
name: "Archive a document"
capability: "docs.archive"
risk: "destructive"
arguments: ["page","archive","{document}","--output","json"]
inputs: ["document"]
result-kind: "documentation-archive"
---

# Archive a document

Archives one external document. No bundled Method Pack role receives `docs.archive` by default.
