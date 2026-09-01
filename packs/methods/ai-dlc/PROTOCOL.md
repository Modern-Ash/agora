# AI-DLC protocol

## Operating pattern

Every phase repeats the AI-DLC loop: the AI drafts a plan from the current
intent, asks the team targeted questions, the humans decide, and the AI
implements the decision. The Product Owner holds every judgement that changes
scope or acceptance.

## Phases and their stages

The gates in `METHOD.md` are binding. The bulleted stages below are the expected
activities inside each phase — a checklist for the team, never evaluated by a
gate.

- **Initiation** — capture the business intent; agree the working scope; record
  constraints and assumptions as the `intent` artifact.
- **Ideation** — mob elaboration: expand intent into requirements, stories, and
  units of work; resolve open questions; register `units-of-work`.
- **Inception** — propose the domain model and architecture; map each unit of
  work to acceptance criteria; register `architecture` and `domain-model`.
- **Construction** — mob construction: propose code and tests per unit of work;
  record evidence that each criterion is built and then verified.
- **Operation** — infrastructure-as-code and deployment; record deployment
  evidence; confirm acceptance in the running environment.

## Vocabulary

- A **bolt** is one pass through a phase, measured in hours or days rather than
  weeks.
- A **unit of work** replaces the epic: the smallest slice of intent that can be
  elaborated, built, and accepted on its own.

## Mob review

"Mob elaboration" and "mob construction" are practices the team runs through
`review` actions and shared sessions. This pack version does not govern
concurrent multi-holder gate approval; each gate records the approvals its
policy names.

## Rework

Failed verification returns work to `construction`; a requirements gap returns it
to `inception`. The specification does not change mid-cycle without a new draft.
