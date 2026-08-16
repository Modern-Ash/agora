---
schema: "agora/tool/v1"
id: "security-scanning"
name: "Security scanning"
version: "1.0.0"
dependencies: []
category: "security"
executable: "securityctl"
authentication-reference: "team-security-profile"
timeout-seconds: 300
max-output-bytes: 1048576
---

# Security scanning

Provides a provider-neutral, read-only contract for bounded code, dependency, and secret scanning
alerts. Adapters must redact secret values before output becomes durable.
