---
schema: "agora/tool-operation/v1"
id: "approve"
name: "Approve a code review"
capability: "review.decide"
risk: "write"
arguments: ["approve","--review","{review}","--body","{body}"]
inputs: ["review","body"]
result-kind: "code-review-decision"
---

# Approve a code review

Records an external approval. Agora lifecycle approval remains a distinct governed operation.
