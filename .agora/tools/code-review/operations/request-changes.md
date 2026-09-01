---
schema: "agora/tool-operation/v1"
id: "request-changes"
name: "Request code review changes"
capability: "review.decide"
risk: "write"
arguments: ["request-changes","--review","{review}","--body","{body}"]
inputs: ["review","body"]
result-kind: "code-review-decision"
---

# Request code review changes

Records an external request for changes without changing Agora work state implicitly.
