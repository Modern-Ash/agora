---
schema: "agora/gate/v1"
id: "plan-approved"
require-all-criteria: true
required-criterion-stage: "planned"
require-required-artifacts: true
required-artifacts: ["implementation-plan"]
require-successful-evidence: false
required-approval-roles: []
---

# Plan approval gate

Implementation cannot begin until an implementation plan is registered and the Spec Owner has
confirmed that every acceptance criterion is covered by that plan.
