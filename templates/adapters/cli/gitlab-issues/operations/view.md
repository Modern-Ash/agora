---
schema: "agora/tool-operation/v1"
id: "view"
name: "View a GitLab issue"
capability: "issue.read"
risk: "read"
arguments: ["issue","view","{issue}","--output","json"]
inputs: ["issue"]
result-kind: "work-item"
---

# View a GitLab issue

Returns one issue from the selected project as JSON. The input may be an issue IID or full URL.
