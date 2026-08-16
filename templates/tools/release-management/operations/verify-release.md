---
schema: "agora/tool-operation/v1"
id: "verify-release"
name: "Verify a release"
capability: "release.read"
risk: "read"
arguments: ["release","verify","--project","{project}","--release","{release}","--output","json"]
inputs: ["project","release"]
result-kind: "release-verification"
---

# Verify a release

Verifies the provider's cryptographic attestation for one release.
