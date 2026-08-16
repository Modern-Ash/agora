---
schema: "agora/tool-operation/v1"
id: "archive"
name: "Archive Confluence content"
capability: "docs.archive"
risk: "destructive"
arguments: ["confluence","content","archive","{document}","--yes","--output","json"]
inputs: ["document"]
result-kind: "documentation-archive"
---

# Archive Confluence content

Archives one Confluence content object non-interactively. No bundled Method Pack role receives
`docs.archive` by default.
