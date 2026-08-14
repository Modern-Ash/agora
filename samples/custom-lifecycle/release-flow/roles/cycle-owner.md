---
schema: "agora/role/v1"
id: "cycle-owner"
required-capabilities: ["prioritization", "acceptance"]
allowed-actor-kinds: ["human", "ai-agent", "swarm"]
allowed-actions: ["work.create", "delegation.accept", "delegation.manage", "work.transition", "criterion.satisfy", "approval.add", "handoff.create", "handoff.manage"]
allowed-tool-capabilities: ["repository.read", "issue.read", "issue.write", "docs.read"]
---

# Cycle Owner

Selects outcomes, accepts criteria, and owns entry into and release from the lifecycle.
