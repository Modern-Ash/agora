---
schema: "agora/tool-operation/v1"
id: "view-release"
name: "View a GitHub release"
capability: "release.read"
risk: "read"
arguments: ["release","view","{release}","--repo","{project}","--json","assets,author,body,createdAt,databaseId,isDraft,isImmutable,isPrerelease,name,publishedAt,tagName,targetCommitish,url"]
inputs: ["project","release"]
result-kind: "release"
---

# View a GitHub release

Returns one release and its assets as JSON.
