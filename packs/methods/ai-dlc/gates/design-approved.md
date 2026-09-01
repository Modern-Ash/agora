---
schema: "agora/gate/v1"
id: "design-approved"
require-all-criteria: true
required-criterion-stage: "designed"
require-required-artifacts: true
required-artifacts: ["architecture", "domain-model"]
require-successful-evidence: false
required-approval-roles: ["architect", "product-owner"]
require-resolved-clarifications: false
---

# Design gate

Construction cannot begin until every criterion has reached `designed`, the
`architecture` and `domain-model` artifacts are registered, and both the
Architect and the Product Owner have approved.
