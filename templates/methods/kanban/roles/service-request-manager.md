---
schema: "agora/role/v1"
id: "service-request-manager"
required-capabilities: ["demand-management", "acceptance"]
allowed-actor-kinds: ["human", "ai-agent", "swarm"]
allowed-actions: ["actor.key.recover", "actor.key.revoke", "actor.key.rotate", "actor.runtime.update", "work.create", "work.cancel", "delegation.accept", "delegation.reject", "delegation.cancel", "criterion.satisfy", "work.transition", "evidence.add", "approval.add", "handoff.create"]
allowed-tool-capabilities: ["repository.read", "issue.read", "issue.write", "issue.transition", "docs.read", "docs.write"]
---

# Service Request Manager

Owns demand intake, ordering, service expectations, and acceptance criteria.
