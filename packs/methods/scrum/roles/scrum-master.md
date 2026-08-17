---
schema: "agora/role/v1"
id: "scrum-master"
required-capabilities: ["facilitation", "governance"]
allowed-actor-kinds: ["human", "ai-agent", "swarm"]
allowed-actions: ["actor.key.recover", "actor.key.revoke", "actor.key.rotate", "actor.runtime.update", "swarm.assign", "criterion.satisfy", "work.transition", "work.block", "work.resume", "delegation.manage", "delegation.block", "delegation.resume", "evidence.add", "usage.add", "handoff.create", "handoff.manage"]
allowed-tool-capabilities: ["repository.read", "repository.governance.read", "review.read", "review.write", "issue.read", "ci.read", "docs.read", "cloud.read", "observability.read", "incident.write", "release.read", "security.read", "portfolio.read"]
allowed-environments: ["*"]
---

# Scrum Master

Protects the protocol, exposes impediments, coordinates handoffs, and ensures that gates are applied.
