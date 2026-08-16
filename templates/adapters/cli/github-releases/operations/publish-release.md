---
schema: "agora/tool-operation/v1"
id: "publish-release"
name: "Publish a GitHub release"
capability: "release.publish"
risk: "write"
arguments: ["release","create","{release}","{artifact}","--repo","{project}","--title","{title}","--notes","{notes}","--verify-tag","--fail-on-no-commits"]
inputs: ["project","release","title","notes","artifact"]
result-kind: "release"
---

# Publish a GitHub release

Publishes an existing remote tag and explicit artifact without allowing implicit tag creation.
