---
schema: "agora/tool-operation/v1"
id: "merge"
name: "Merge a code review"
capability: "review.merge"
risk: "destructive"
arguments: ["merge","--review","{review}","--method","{method}"]
inputs: ["review","method"]
input-values: {"method":["merge","squash","rebase"]}
result-kind: "code-review-merge"
---

# Merge a code review

Merges one accepted change request. No bundled role grants `review.merge`; projects must opt in
through reviewed role and environment policy.
