---
schema: "agora/tool-operation/v1"
id: "search"
name: "Search knowledge"
capability: "docs.read"
risk: "read"
arguments: ["page","search","--space","{space}","--query","{query}","--output","json"]
inputs: ["space","query"]
result-kind: "document-list"
---

# Search knowledge

Returns documents matching one query in a provider-neutral space.
