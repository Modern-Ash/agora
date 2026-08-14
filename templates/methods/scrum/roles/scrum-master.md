---
schema: "agora/role/v1"
id: "scrum-master"
required-capabilities: ["facilitation", "governance"]
allowed-actor-kinds: ["human", "ai-agent", "swarm"]
allowed-actions: ["work.transition", "work.block", "work.resume", "delegation.manage", "delegation.block", "delegation.resume", "evidence.add", "handoff.create", "handoff.manage"]
allowed-tool-capabilities: ["repository.read", "issue.read", "ci.read", "docs.read"]
---

# Scrum Master

Protects the protocol, exposes impediments, coordinates handoffs, and ensures that gates are applied.
