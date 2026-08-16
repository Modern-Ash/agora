---
schema: "agora/tool-operation/v1"
id: "request-changes"
name: "Request GitHub pull request changes"
capability: "review.decide"
risk: "write"
arguments: ["pr","review","{review}","--request-changes","--body","{body}"]
inputs: ["review","body"]
result-kind: "code-review-decision"
---

# Request GitHub pull request changes

Submits one request-for-changes review.
