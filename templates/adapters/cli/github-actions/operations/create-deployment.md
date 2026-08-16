---
schema: "agora/tool-operation/v1"
id: "create-deployment"
name: "Create a GitHub deployment"
capability: "deployment.create"
risk: "write"
environment-required: true
arguments: ["api","--method","POST","repos/{repository}/deployments","--raw-field","ref={artifact}","--raw-field","environment={environment}","--field","auto_merge=false"]
inputs: ["repository","environment","artifact"]
result-kind: "deployment"
---

# Create a GitHub deployment

Creates a deployment through the authenticated GitHub API. `repository` uses `owner/name` format and
`artifact` is an immutable commit SHA or reviewed Git ref. Bundled roles do not receive
`deployment.create` authority.
