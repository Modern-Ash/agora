---
schema: "agora/role/v1"
id: "maker"
required-capabilities: ["delivery"]
allowed-actor-kinds: ["human", "ai-agent", "swarm", "automation"]
allowed-actions: ["work.transition", "work.block", "work.resume", "work.delegate", "delegation.collect", "artifact.add", "evidence.add", "handoff.create"]
allowed-tool-capabilities: ["repository.read", "repository.write", "ci.read", "ci.run"]
---

# Maker

Produces the outcome using the project-selected languages, runtimes, tools, and environments.
