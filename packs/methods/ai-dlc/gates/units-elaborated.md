---
schema: "agora/gate/v1"
id: "units-elaborated"
require-all-criteria: true
required-criterion-stage: "elaborated"
require-required-artifacts: true
required-artifacts: ["units-of-work"]
require-successful-evidence: false
required-approval-roles: ["product-owner"]
require-resolved-clarifications: false
---

# Elaboration gate

Inception cannot begin until every acceptance criterion has reached `elaborated`,
a `units-of-work` artifact is registered, and the Product Owner has approved.
