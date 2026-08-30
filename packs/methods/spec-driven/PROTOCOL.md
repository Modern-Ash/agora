# Spec-Driven protocol

The Spec Owner drafts the specification, resolves every open question, and holds final acceptance.
The Developer plans, implements, and verifies against the accepted specification. A spec cannot leave
drafting until its criteria are satisfied, a `spec` artifact is registered, and a current
clarification run leaves no unanswered question — clarification is a gate, not a convention.

Implementation cannot begin until an `implementation-plan` artifact is registered and the Spec
Owner marks every criterion `planned`. Planning coverage is therefore a second gate, not an implied
side effect of advancing the work state.

The latest guided clarification run is binding only for the `spec-clarified` gate: it must cover the
current work and specification inputs and leave no unanswered question. Checklists remain
non-binding, while consistency reports and generated Gherkin may support verification. None of
these tools satisfy a criterion or transition work without the existing gate and role actions.

The same actor may hold both roles when project policy allows it, but the two responsibilities stay
distinguishable: clarifying scope is not the same action as implementing it.

Failed verification returns work to `implementing` for rework rather than inventing a new state; the
specification does not change mid-cycle without a new draft.
