---
schema: "agora/role/v1"
id: "delivery"
required-capabilities: ["implementation"]
allowed-actor-kinds: ["human", "ai-agent", "swarm"]
allowed-actions: ["work.transition", "work.block", "work.resume", "work.delegate", "delegation.collect", "artifact.add", "evidence.add", "handoff.create"]
allowed-tool-capabilities: ["repository.read", "repository.write", "ci.read", "ci.run"]
---

# Delivery

Produces the requested change and its required technical artifacts and evidence.
