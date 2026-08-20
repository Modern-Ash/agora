---
schema: "agora/role/v1"
id: "spec-owner"
required-capabilities: ["specification", "acceptance"]
allowed-actor-kinds: ["human", "ai-agent", "swarm"]
allowed-actions: ["actor.key.recover", "actor.key.revoke", "actor.key.rotate", "actor.runtime.update", "swarm.assign", "work.create", "work.decompose", "work.cancel", "work.clarify", "work.verify-consistency", "work.gherkin", "delegation.accept", "delegation.reject", "delegation.cancel", "criterion.satisfy", "work.transition", "artifact.add", "evidence.add", "checklist.add", "checklist.check", "usage.add", "budget.amend", "approval.add", "approval.delegate", "approval.delegation.revoke", "gate.waive", "handoff.create"]
allowed-tool-capabilities: ["repository.read", "repository.governance.read", "review.read", "review.write", "review.decide", "issue.read", "issue.write", "issue.transition", "docs.read", "docs.write", "release.read", "security.read", "portfolio.read", "portfolio.write"]
allowed-environments: ["*"]
---

# Spec Owner

Owns the specification: drafts it, resolves every open question, and holds final acceptance. An AI or
swarm may perform the role only when project policy does not reserve final acceptance for a human.
