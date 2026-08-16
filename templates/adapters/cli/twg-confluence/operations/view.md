---
schema: "agora/tool-operation/v1"
id: "view"
name: "View a Confluence page"
capability: "docs.read"
risk: "read"
arguments: ["confluence","content","get","{document}","--detail","full","--format","html","--include-metadata","--output","json","--output-summary","auto","--agent-fields","@evidence"]
inputs: ["document"]
result-kind: "documentation"
---

# View a Confluence page

Returns the complete HTML body, metadata, version, and opaque snapshot token needed for a
concurrency-safe update.
