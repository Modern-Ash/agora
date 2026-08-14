---
schema: "agora/role/v1"
id: "cycle-owner"
required-capabilities: ["prioritization", "acceptance"]
allowed-actor-kinds: ["human", "ai-agent", "swarm"]
allowed-actions: ["work.create", "work.transition", "criterion.satisfy"]
---

# Cycle Owner

Selects outcomes, accepts criteria, and owns entry into and release from the lifecycle.
