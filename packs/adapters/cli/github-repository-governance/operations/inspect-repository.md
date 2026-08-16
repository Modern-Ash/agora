---
schema: "agora/tool-operation/v1"
id: "inspect-repository"
name: "Inspect GitHub repository governance"
capability: "repository.governance.read"
risk: "read"
arguments: ["repo","view","{project}","--json","nameWithOwner,defaultBranchRef,deleteBranchOnMerge,isArchived,isPrivate,mergeCommitAllowed,rebaseMergeAllowed,squashMergeAllowed,viewerPermission"]
inputs: ["project"]
result-kind: "repository-governance"
---

# Inspect GitHub repository governance

Returns selected repository governance fields as JSON.
