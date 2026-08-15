---
schema: "agora/role/v1"
id: "delivery"
required-capabilities: ["implementation"]
allowed-actor-kinds: ["human", "ai-agent", "swarm"]
allowed-actions: ["actor.runtime.update", "work.transition", "work.block", "work.resume", "work.delegate", "delegation.collect", "artifact.add", "evidence.add", "handoff.create"]
allowed-tool-capabilities: ["repository.read", "repository.write", "issue.read", "ci.read", "ci.run", "docs.read", "docs.write", "cloud.read", "cloud.plan", "observability.read", "incident.write"]
---

# Delivery

Produces the requested change and its required technical artifacts and evidence.
