---
schema: "agora/tool-operation/v1"
id: "checks"
name: "Inspect code review checks"
capability: "review.read"
risk: "read"
arguments: ["checks","--review","{review}"]
inputs: ["review"]
result-kind: "code-review-checks"
---

# Inspect code review checks

Returns bounded CI check state associated with one change request.
