---
schema: "agora/tool-operation/v1"
id: "verify-release"
name: "Verify a GitHub release"
capability: "release.read"
risk: "read"
arguments: ["release","verify","{release}","--repo","{project}","--format","json"]
inputs: ["project","release"]
result-kind: "release-verification"
---

# Verify a GitHub release

Verifies the release attestation and returns asset digest metadata as JSON.
