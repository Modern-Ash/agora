---
schema: "agora/role/v1"
id: "product-owner"
required-capabilities: ["backlog-management", "acceptance"]
allowed-actor-kinds: ["human", "ai-agent", "swarm"]
allowed-actions: ["actor.key.recover", "actor.key.revoke", "actor.key.rotate", "actor.runtime.update", "swarm.assign", "work.create", "work.decompose", "work.cancel", "delegation.accept", "delegation.reject", "delegation.cancel", "criterion.satisfy", "work.transition", "evidence.add", "approval.add", "gate.waive", "handoff.create"]
allowed-tool-capabilities: ["repository.read", "issue.read", "issue.write", "issue.transition", "docs.read", "docs.write"]
---

# Product Owner

Owns objective clarity, ordering, acceptance criteria, and acceptance decisions. An AI or swarm may
perform the role only when project policy does not reserve final acceptance for a human.
