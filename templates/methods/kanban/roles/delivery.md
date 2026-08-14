---
schema: "agora/role/v1"
id: "delivery"
required-capabilities: ["implementation"]
allowed-actor-kinds: ["human", "ai-agent", "swarm"]
allowed-actions: ["work.transition", "artifact.add", "evidence.add"]
---

# Delivery

Produces the requested change and its required technical artifacts and evidence.
