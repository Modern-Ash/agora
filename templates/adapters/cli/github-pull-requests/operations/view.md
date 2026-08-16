---
schema: "agora/tool-operation/v1"
id: "view"
name: "View a GitHub pull request"
capability: "review.read"
risk: "read"
arguments: ["pr","view","{review}","--json","number,title,body,state,isDraft,mergeable,reviewDecision,headRefName,baseRefName,url,author,reviews,statusCheckRollup"]
inputs: ["review"]
result-kind: "code-review"
---

# View a GitHub pull request

Returns one pull request and its bounded review and check summary as JSON.
