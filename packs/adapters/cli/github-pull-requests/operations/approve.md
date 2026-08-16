---
schema: "agora/tool-operation/v1"
id: "approve"
name: "Approve a GitHub pull request"
capability: "review.decide"
risk: "write"
arguments: ["pr","review","{review}","--approve","--body","{body}"]
inputs: ["review","body"]
result-kind: "code-review-decision"
---

# Approve a GitHub pull request

Submits one approval review without satisfying an Agora lifecycle gate implicitly.
