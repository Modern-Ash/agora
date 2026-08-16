---
schema: "agora/tool-operation/v1"
id: "view"
name: "View a code review"
capability: "review.read"
risk: "read"
arguments: ["view","--review","{review}"]
inputs: ["review"]
result-kind: "code-review"
---

# View a code review

Returns the current change-request metadata and review state.
