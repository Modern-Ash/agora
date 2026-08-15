---
schema: "agora/tool-operation/v1"
id: "create"
name: "Create a GitHub issue"
capability: "issue.write"
risk: "write"
arguments: ["issue","create","--repo","{project}","--type","{type}","--title","{title}","--body","{description}"]
inputs: ["project","type","title","description"]
result-kind: "work-item"
---

# Create a GitHub issue

Creates a non-interactive issue in the `owner/repository` project and returns its URL.
