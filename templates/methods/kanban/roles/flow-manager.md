---
schema: "agora/role/v1"
id: "flow-manager"
required-capabilities: ["flow-management", "governance"]
allowed-actor-kinds: ["human", "ai-agent", "swarm"]
allowed-actions: ["work.transition", "delegation.manage", "evidence.add", "handoff.create", "handoff.manage"]
allowed-tool-capabilities: ["repository.read", "issue.read", "ci.read", "docs.read"]
---

# Flow Manager

Applies WIP limits, identifies blocked flow, and enforces entry and exit policies.
