# Sessions

Each directory contains a durable runtime selection and compiled context created by `agora start`.
Completed sessions retain bounded provider output in `RESULT.md` and a deterministic, concise
`SUMMARY.md` linked from the project Activity Ledger. `PROGRESS.md` contains only bounded execution
milestones reported by the bound executor; it must never contain chain-of-thought or credentials.
`SESSION.md` distinguishes the responsible role holder from an optional AI executor so assistance
does not silently transfer ownership. Conversation history remains external unless its material
outcome is recorded in Agora files.
