---
schema: "agora/role/v1"
id: "product-owner"
required-capabilities: ["specification", "acceptance"]
allowed-actor-kinds: ["human", "ai-agent", "swarm"]
allowed-actions: ["actor.key.recover", "actor.key.revoke", "actor.key.rotate", "actor.runtime.update", "swarm.assign", "work.create", "work.decompose", "work.cancel", "work.clarify", "work.verify-consistency", "work.gherkin", "delegation.accept", "delegation.reject", "delegation.cancel", "criterion.satisfy", "work.transition", "artifact.add", "evidence.add", "checklist.add", "checklist.check", "usage.add", "budget.amend", "approval.add", "approval.delegate", "approval.delegation.revoke", "gate.waive", "handoff.create"]
allowed-tool-capabilities: ["repository.read", "repository.governance.read", "review.read", "review.write", "review.decide", "issue.read", "issue.write", "issue.transition", "docs.read", "docs.write", "release.read", "security.read", "portfolio.read", "portfolio.write"]
allowed-environments: ["*"]
---

# Product Owner

Frames the business intent, elaborates units of work with the team, and holds
final acceptance. In AI-DLC terms this is the human who "makes the critical
decisions". An AI or swarm may hold the role only when project policy does not
reserve final acceptance for a human.
