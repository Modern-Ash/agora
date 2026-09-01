---
schema: "agora/role/v1"
id: "operator"
required-capabilities: ["implementation"]
allowed-actor-kinds: ["human", "ai-agent", "swarm", "automation"]
allowed-actions: ["criterion.satisfy", "work.transition", "artifact.add", "evidence.add", "checklist.add", "checklist.check", "handoff.create"]
allowed-tool-capabilities: ["repository.read", "ci.read", "ci.run", "cloud.read", "release.read"]
allowed-environments: ["*"]
---

# Operator

Owns the Operation phase: manages infrastructure-as-code and deployment, records
deployment evidence, and returns the work to Construction when verification
fails. Write and apply capabilities remain opt-in through project environment
policy.
