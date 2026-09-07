---
schema: "agora/tool-operation/v1"
id: "comment"
name: "Comment on a code review"
capability: "review.write"
risk: "write"
arguments: ["comment","--review","{review}","--body","{body}"]
inputs: ["review","body"]
result-kind: "code-review-comment"
---

# Comment on a code review

Adds one attributable review comment.
