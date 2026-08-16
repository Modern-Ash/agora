---
schema: "agora/tool-operation/v1"
id: "checks"
name: "Inspect GitLab merge request checks"
capability: "review.read"
risk: "read"
arguments: ["ci","get","--merge-request","{review}","--output","json"]
inputs: ["review"]
result-kind: "code-review-checks"
---

# Inspect GitLab merge request checks

Returns the head pipeline associated with one merge-request IID as JSON.
