---
schema: "agora/tool-operation/v1"
id: "comment"
name: "Comment on a GitLab merge request"
capability: "review.write"
risk: "write"
arguments: ["mr","note","--message","{body}","{review}"]
inputs: ["review","body"]
result-kind: "code-review-comment"
---

# Comment on a GitLab merge request

Adds one non-interactive merge-request comment.
