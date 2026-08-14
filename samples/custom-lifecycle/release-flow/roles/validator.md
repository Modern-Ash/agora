---
schema: "agora/role/v1"
id: "validator"
required-capabilities: ["validation"]
allowed-actor-kinds: ["human", "ai-agent", "swarm", "service", "automation"]
allowed-actions: ["work.transition", "work.block", "work.resume", "evidence.add", "handoff.create"]
allowed-tool-capabilities: ["repository.read", "ci.read", "docs.read"]
---

# Validator

Produces evidence against the acceptance criteria and project policy.
