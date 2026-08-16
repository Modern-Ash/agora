---
schema: "agora/tool-operation/v1"
id: "comment"
name: "Comment on a GitHub pull request"
capability: "review.write"
risk: "write"
arguments: ["pr","comment","{review}","--body","{body}"]
inputs: ["review","body"]
result-kind: "code-review-comment"
---

# Comment on a GitHub pull request

Adds one non-interactive pull-request comment.
