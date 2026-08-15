---
schema: "agora/tool-operation/v1"
id: "comment"
name: "Comment on a GitHub issue"
capability: "issue.write"
risk: "write"
arguments: ["issue","comment","{issue}","--body","{body}"]
inputs: ["issue","body"]
result-kind: "work-item-comment"
---

# Comment on a GitHub issue

Adds one non-interactive issue comment. The issue may be a number or full URL.
