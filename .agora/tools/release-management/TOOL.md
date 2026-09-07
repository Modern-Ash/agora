---
schema: "agora/tool/v1"
id: "release-management"
name: "Release management"
version: "1.0.0"
dependencies: []
category: "release"
executable: "releasectl"
authentication-reference: "team-release-profile"
timeout-seconds: 600
max-output-bytes: 1048576
---

# Release management

Provides a provider-neutral contract for release discovery, publication from an existing immutable
tag and artifact, and cryptographic release verification.
