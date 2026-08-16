---
schema: "agora/tool-operation/v1"
id: "create"
name: "Create a Confluence page draft"
capability: "docs.write"
risk: "write"
arguments: ["confluence","content","create","--space-id","{space}","--parent-id","{parent}","--content-type","page","--title","{title}","--body","{body}","--format","html","--draft","--ack-body-formats","--yes","--output","json"]
inputs: ["space","parent","title","body"]
result-kind: "documentation"
---

# Create a Confluence page draft

Creates one page draft from an explicit HTML body. Publication remains a separate governed
operation.
