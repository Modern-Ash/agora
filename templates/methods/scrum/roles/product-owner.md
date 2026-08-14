---
schema: "agora/role/v1"
id: "product-owner"
required-capabilities: ["backlog-management", "acceptance"]
allowed-actor-kinds: ["human", "ai-agent", "swarm"]
allowed-actions: ["work.create", "criterion.satisfy", "work.transition", "evidence.add"]
---

# Product Owner

Owns objective clarity, ordering, acceptance criteria, and acceptance decisions. An AI or swarm may
perform the role only when project policy does not reserve final acceptance for a human.
