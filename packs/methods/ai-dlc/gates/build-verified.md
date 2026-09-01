---
schema: "agora/gate/v1"
id: "build-verified"
require-all-criteria: true
required-criterion-stage: "verified"
require-required-artifacts: false
require-successful-evidence: true
required-approval-roles: ["quality-reviewer"]
require-resolved-clarifications: false
---

# Build gate

Operation cannot begin until every criterion has reached `verified`, at least one
successful evidence record exists, and the Quality Reviewer has approved.
