# Instructions for coding agents

- Preserve Agora's programming-language, LLM-provider, model, and development-process independence.
- Do not introduce LLM SDKs or provider dependencies into the core CLI.
- Implement Agora scripts and automation in Python, not JavaScript or TypeScript.
- Keep the protocol Markdown-first, human-readable, and portable across agent environments.
- Add tests for domain rules and their failure paths.
- Update templates and documentation whenever the installed protocol changes.
- Treat filesystem and Git as the persistent collaboration substrate.
- Keep environment-specific output in integration adapters.
- Treat Scrum and Kanban as bundled examples, never as privileged core workflows.
- Prefer small, reviewable changes and abstractions backed by a concrete lifecycle requirement.
