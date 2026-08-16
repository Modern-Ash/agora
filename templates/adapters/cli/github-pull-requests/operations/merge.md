---
schema: "agora/tool-operation/v1"
id: "merge"
name: "Merge a GitHub pull request"
capability: "review.merge"
risk: "destructive"
arguments: ["pr","merge","{review}","--{method}","--delete-branch"]
inputs: ["review","method"]
input-values: {"method":["merge","squash","rebase"]}
result-kind: "code-review-merge"
---

# Merge a GitHub pull request

Merges one pull request with an explicitly selected GitHub merge method and deletes its remote head
branch. Projects must grant `review.merge` explicitly.
