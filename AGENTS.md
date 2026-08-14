# Instructions for coding agents

- Preserve Agora's programming-language, LLM-provider, model, and development-process independence.
- Do not introduce LLM SDKs or provider dependencies into the core CLI.
- Implement Agora scripts and automation in Python, not JavaScript or TypeScript.
- Keep the protocol Markdown-first, human-readable, and portable across agent environments.
- Add tests for domain rules and their failure paths.
- Update templates and documentation whenever the installed protocol changes.
- Treat filesystem and Git as the persistent collaboration substrate.
- Use Conventional Commits 1.0.0 for every commit: `<type>[optional scope][!]: <description>` with
  bodies and footers separated by a blank line.
- Keep environment-specific output in integration adapters.
- Keep Tool Pack commands structured, shell-free, and free of credential inputs.
- Keep registry indexes and snapshots Markdown-first; verify remote releases before extraction,
  validate every contained pack before copying, persist provenance, and preserve
  project-over-user-over-bundled precedence.
- Keep registry trust public-only and Markdown-first; preserve project-over-user key precedence and
  never allow explicit key input to bypass a persisted revocation.
- Keep registry updates preview-first, forward-only, authenticated, transactional, and historically
  auditable; never refresh installed packs implicitly.
- Treat Scrum and Kanban as bundled examples, never as privileged core workflows.
- Preserve recursive swarm cycle checks and configured delegation depth.
- Preserve explicit child-work acceptance and reference-based result collection across swarms.
- Prefer small, reviewable changes and abstractions backed by a concrete lifecycle requirement.
