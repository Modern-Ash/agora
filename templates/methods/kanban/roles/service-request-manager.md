---
schema: "agora/role/v1"
id: "service-request-manager"
required-capabilities: ["demand-management", "acceptance"]
allowed-actor-kinds: ["human", "ai-agent", "swarm"]
allowed-actions: ["work.create", "criterion.satisfy", "work.transition", "evidence.add"]
---

# Service Request Manager

Owns demand intake, ordering, service expectations, and acceptance criteria.
