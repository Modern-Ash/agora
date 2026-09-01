---
schema: "agora/tool/v1"
id: "portfolio-management"
name: "Portfolio management"
version: "1.0.0"
dependencies: []
category: "portfolio"
executable: "portfolioctl"
authentication-reference: "team-portfolio-profile"
timeout-seconds: 300
max-output-bytes: 1048576
---

# Portfolio management

Provides a provider-neutral contract for project portfolios and references to existing work items.
Destructive deletion and provider-specific field mutation are intentionally outside the contract.
