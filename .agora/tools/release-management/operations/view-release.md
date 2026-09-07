---
schema: "agora/tool-operation/v1"
id: "view-release"
name: "View a release"
capability: "release.read"
risk: "read"
arguments: ["release","view","--project","{project}","--release","{release}","--output","json"]
inputs: ["project","release"]
result-kind: "release"
---

# View a release

Returns one release and its published asset identities.
