---
schema: "agora/role/v1"
id: "developer"
required-capabilities: ["implementation"]
allowed-actor-kinds: ["human", "ai-agent", "swarm"]
allowed-actions: ["work.transition", "work.delegate", "delegation.collect", "artifact.add", "evidence.add", "handoff.create"]
allowed-tool-capabilities: ["repository.read", "repository.write", "ci.read", "ci.run"]
---

# Developer

Plans, implements, tests, and documents the increment using only tools allowed by project policy.
