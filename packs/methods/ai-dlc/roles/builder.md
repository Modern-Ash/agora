---
schema: "agora/role/v1"
id: "builder"
required-capabilities: ["implementation"]
allowed-actor-kinds: ["human", "ai-agent", "swarm", "automation"]
allowed-actions: ["work.decompose", "criterion.satisfy", "work.transition", "artifact.add", "evidence.add", "checklist.add", "checklist.check", "handoff.create"]
allowed-tool-capabilities: ["repository.read", "repository.write", "review.read", "ci.read", "ci.run"]
allowed-environments: ["*"]
---

# Builder

Owns the Construction phase: proposes code and tests through mob construction and
records the evidence that each acceptance criterion is built and verified. Merge,
release, and deployment authority are never implied by this role.
