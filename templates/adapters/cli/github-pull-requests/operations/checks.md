---
schema: "agora/tool-operation/v1"
id: "checks"
name: "Inspect GitHub pull request checks"
capability: "review.read"
risk: "read"
arguments: ["pr","checks","{review}","--json","name,state,link,bucket"]
inputs: ["review"]
result-kind: "code-review-checks"
---

# Inspect GitHub pull request checks

Returns the current checks associated with one pull request.
