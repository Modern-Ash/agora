---
schema: "agora/role/v1"
id: "developer"
required-capabilities: ["implementation"]
allowed-actor-kinds: ["human", "ai-agent", "swarm"]
allowed-actions: ["work.transition", "work.block", "work.resume", "work.delegate", "delegation.collect", "artifact.add", "evidence.add", "handoff.create"]
allowed-tool-capabilities: ["repository.read", "repository.write", "issue.read", "ci.read", "ci.run", "docs.read", "docs.write", "cloud.read", "cloud.plan", "observability.read", "incident.write"]
---

# Developer

Plans, implements, tests, and documents the increment using only tools allowed by project policy.
