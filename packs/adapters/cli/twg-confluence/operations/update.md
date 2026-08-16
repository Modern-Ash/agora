---
schema: "agora/tool-operation/v1"
id: "update"
name: "Update a Confluence page draft"
capability: "docs.write"
risk: "write"
arguments: ["confluence","content","update","{document}","--snapshot-token","{snapshot-token}","--title","{title}","--body","{body}","--format","html","--draft","--ack-body-formats","--yes","--output","json"]
inputs: ["document","title","body","snapshot-token"]
result-kind: "documentation"
---

# Update a Confluence page draft

Replaces a draft title and HTML body only when the opaque token from the latest full view still
matches. Confluence rejects a stale token rather than silently overwriting concurrent edits.
