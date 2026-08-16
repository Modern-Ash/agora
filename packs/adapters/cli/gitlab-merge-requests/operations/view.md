---
schema: "agora/tool-operation/v1"
id: "view"
name: "View a GitLab merge request"
capability: "review.read"
risk: "read"
arguments: ["mr","view","{review}","--output","json"]
inputs: ["review"]
result-kind: "code-review"
---

# View a GitLab merge request

Returns one merge request as JSON. The review may be an IID, branch, or full URL accepted by `glab`.
