# Instructions for coding agents

- Preserve Agora's provider independence.
- Do not introduce LLM SDKs or provider dependencies into the core CLI.
- Keep the protocol Markdown-first, human-readable, and portable across agent environments.
- Add tests for domain rules and their failure paths.
- Update templates and documentation whenever the installed protocol changes.
- Treat filesystem and Git as the persistent collaboration substrate.
- Keep environment-specific output in integration adapters.
- Prefer small, reviewable changes and avoid speculative methodology abstractions.
