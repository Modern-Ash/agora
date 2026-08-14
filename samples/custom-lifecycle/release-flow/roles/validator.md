---
schema: "agora/role/v1"
id: "validator"
required-capabilities: ["validation"]
allowed-actor-kinds: ["human", "ai-agent", "swarm", "service", "automation"]
allowed-actions: ["work.transition", "evidence.add"]
---

# Validator

Produces evidence against the acceptance criteria and project policy.
