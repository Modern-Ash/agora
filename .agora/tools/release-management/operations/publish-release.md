---
schema: "agora/tool-operation/v1"
id: "publish-release"
name: "Publish a release"
capability: "release.publish"
risk: "write"
arguments: ["release","publish","--project","{project}","--release","{release}","--title","{title}","--notes","{notes}","--artifact","{artifact}","--verify-tag","--output","json"]
inputs: ["project","release","title","notes","artifact"]
result-kind: "release"
---

# Publish a release

Publishes one existing immutable tag with an explicit artifact. No bundled role grants
`release.publish`; projects must opt in with reviewed policy, evidence, and approval.
