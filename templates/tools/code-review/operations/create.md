---
schema: "agora/tool-operation/v1"
id: "create"
name: "Create a code review"
capability: "review.write"
risk: "write"
arguments: ["create","--project","{project}","--base","{base}","--head","{head}","--title","{title}","--description","{description}"]
inputs: ["project","base","head","title","description"]
result-kind: "code-review"
---

# Create a code review

Creates one change request from an existing head branch without pushing or changing local Git state.
