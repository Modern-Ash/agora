---
schema: "agora/tool-operation/v1"
id: "comment"
name: "Comment on a GitLab issue"
capability: "issue.write"
risk: "write"
arguments: ["issue","note","{issue}","--message","{body}"]
inputs: ["issue","body"]
result-kind: "work-item-comment"
---

# Comment on a GitLab issue

Adds one non-interactive issue comment. The issue may be an IID or full URL.
