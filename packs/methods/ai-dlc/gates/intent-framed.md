---
schema: "agora/gate/v1"
id: "intent-framed"
require-all-criteria: false
require-required-artifacts: true
required-artifacts: ["intent"]
require-successful-evidence: false
required-approval-roles: []
require-resolved-clarifications: true
---

# Intent gate

Ideation cannot begin until the business intent is registered as an `intent`
artifact and the latest clarification run covers current inputs with no open
question.
