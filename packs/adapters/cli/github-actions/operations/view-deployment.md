---
schema: "agora/tool-operation/v1"
id: "view-deployment"
name: "View a GitHub deployment"
capability: "ci.read"
risk: "read"
arguments: ["api","repos/{repository}/deployments/{deployment}"]
inputs: ["repository","deployment"]
result-kind: "deployment"
---

# View a GitHub deployment

Returns one deployment through the authenticated GitHub API.
