---
schema: "agora/tool-operation/v1"
id: "create"
name: "Create a GitHub pull request"
capability: "review.write"
risk: "write"
arguments: ["pr","create","--repo","{project}","--base","{base}","--head","{head}","--title","{title}","--body","{description}"]
inputs: ["project","base","head","title","description"]
result-kind: "code-review"
---

# Create a GitHub pull request

Creates one pull request from an already published head branch.
