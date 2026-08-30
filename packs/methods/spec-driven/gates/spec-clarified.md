---
schema: "agora/gate/v1"
id: "spec-clarified"
require-all-criteria: true
required-criterion-stage: "specified"
require-required-artifacts: true
required-artifacts: ["spec"]
require-successful-evidence: false
required-approval-roles: []
require-resolved-clarifications: true
---

# Clarification gate

The specification is not clarified until every acceptance criterion recorded on the work item is
satisfied, its `spec` artifact is registered, and the latest clarification run covers the current
work and specification inputs without leaving an unanswered question. No separate approval role is
required — the Spec Owner is the actor making this transition.
