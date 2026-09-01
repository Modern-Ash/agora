---
schema: "agora/role/v1"
id: "quality-reviewer"
required-capabilities: ["acceptance"]
allowed-actor-kinds: ["human", "ai-agent", "swarm"]
allowed-actions: ["criterion.satisfy", "work.transition", "artifact.add", "evidence.add", "checklist.add", "checklist.check", "approval.add", "handoff.create"]
allowed-tool-capabilities: ["repository.read", "repository.governance.read", "review.read", "review.write", "review.decide", "security.read"]
allowed-environments: ["*"]
---

# Quality Reviewer

Consolidates AI-DLC's two quality-gate reviewers. Confirms that construction
output meets its acceptance criteria and approves the `build-verified` gate;
sends failed work back to Construction.
