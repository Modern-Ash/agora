---
schema: "agora/role/v1"
id: "developer"
required-capabilities: ["implementation"]
allowed-actor-kinds: ["human", "ai-agent", "swarm"]
allowed-actions: ["actor.key.rotate", "actor.runtime.update", "criterion.satisfy", "work.transition", "work.block", "work.resume", "work.verify-consistency", "work.gherkin", "work.delegate", "work.patch", "delegation.collect", "artifact.add", "evidence.add", "checklist.add", "checklist.check", "usage.add", "handoff.create"]
allowed-tool-capabilities: ["repository.read", "repository.write", "repository.governance.read", "review.read", "review.write", "issue.read", "ci.read", "ci.run", "docs.read", "docs.write", "cloud.read", "cloud.plan", "observability.read", "incident.write", "release.read", "security.read", "portfolio.read"]
allowed-environments: ["*"]
---

# Developer

Plans, implements, tests, and verifies the increment against the clarified specification, using only
tools allowed by project policy.
