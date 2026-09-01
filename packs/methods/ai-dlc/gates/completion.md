---
schema: "agora/gate/v1"
id: "completion"
require-all-criteria: true
required-criterion-stage: "accepted"
require-required-artifacts: true
require-successful-evidence: true
required-approval-roles: ["product-owner"]
require-resolved-clarifications: false
---

# Completion gate

The increment is complete only when every criterion has reached `accepted`,
deployment evidence exists, and the Product Owner has approved.
