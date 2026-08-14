---
schema: "agora/role/v1"
id: "service-request-manager"
required-capabilities: ["demand-management", "acceptance"]
allowed-actor-kinds: ["human", "ai-agent", "swarm"]
allowed-actions: ["work.create", "delegation.accept", "criterion.satisfy", "work.transition", "evidence.add", "approval.add", "handoff.create"]
allowed-tool-capabilities: ["repository.read", "issue.read", "issue.write", "docs.read", "docs.write"]
---

# Service Request Manager

Owns demand intake, ordering, service expectations, and acceptance criteria.
