---
schema: "agora/tool-operation/v1"
id: "publish"
name: "Publish a Confluence page draft"
capability: "docs.publish"
risk: "write"
arguments: ["confluence","content","publish","{document}","--content-type","page","--yes","--output","json"]
inputs: ["document"]
result-kind: "documentation-publication"
---

# Publish a Confluence page draft

Publishes one existing page draft non-interactively. No bundled Method Pack role receives
`docs.publish` by default.
