---
schema: "agora/role/v1"
id: "flow-manager"
required-capabilities: ["flow-management", "governance"]
allowed-actor-kinds: ["human", "ai-agent", "swarm"]
allowed-actions: ["work.transition", "evidence.add"]
---

# Flow Manager

Applies WIP limits, identifies blocked flow, and enforces entry and exit policies.
