---
schema: "agora/tool-operation/v1"
id: "create"
name: "Create a GitLab merge request"
capability: "review.write"
risk: "write"
arguments: ["mr","create","--repo","{project}","--target-branch","{base}","--source-branch","{head}","--title","{title}","--description","{description}","--yes"]
inputs: ["project","base","head","title","description"]
result-kind: "code-review"
---

# Create a GitLab merge request

Creates one merge request from an already published source branch without pushing local changes.
