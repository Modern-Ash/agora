---
schema: "agora/role/v1"
id: "architect"
required-capabilities: ["specification"]
allowed-actor-kinds: ["human", "ai-agent", "swarm"]
allowed-actions: ["swarm.assign", "work.decompose", "work.clarify", "work.verify-consistency", "work.gherkin", "criterion.satisfy", "work.transition", "artifact.add", "evidence.add", "checklist.add", "checklist.check", "approval.add", "handoff.create"]
allowed-tool-capabilities: ["repository.read", "repository.governance.read", "docs.read", "docs.write", "review.read"]
allowed-environments: ["*"]
---

# Architect

Owns the Inception phase: turns framed intent into requirements, units of work, a
domain model, and an architecture proposal. Advances the work into Construction
and pulls it back to Inception when a requirements gap surfaces.
