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
- Keep actor private keys outside Agora; persist only public identity and signed verification
  evidence, preserve rotation and revocation history, and bind authorizations to exact durable
  operations and materialized session context before execution.
- Route authenticated lifecycle mutations through prepared `ACTION.md` intents, bind signatures to
  their work preconditions, and reapply all Method Pack rules immediately before mutation.
- Keep Tool Pack commands structured, shell-free, and free of credential inputs.
- Give Tool Packs bounded direct-process timeouts and captured-output limits; describe external
  containers or runners as the isolation boundary for filesystem, network, syscalls, and resources.
- Keep ecosystem Tool Pack capabilities provider-neutral; place Jira, CI/CD, documentation, and
  cloud translation in reviewed external adapters rather than the kernel.
- Prefer a reviewed native provider CLI when it is installed and non-interactive; use a team wrapper
  for normalization and MCP only as an explicit alternative transport.
- Give reviewed CLI adapters a structured local version command and a tested minimum version; never
  infer compatibility from executable presence alone when launching governed work.
- Use an explicit conforming operation subset when a provider CLI cannot implement a full neutral
  contract; never invent generic plan, apply, or destructive semantics.
- Keep CI cancellation and deployment capabilities opt-in; combine production authority with
  explicit Method Pack policy, evidence, and operation approval requirements.
- Keep documentation publication and archival opt-in; treat remote pages as external state and
  persist their identifiers as Agora artifacts or evidence when lifecycle gates require them.
- Keep cloud apply and destruction opt-in; require reviewed immutable plans, external workload
  identity, explicit approvals, and durable evidence appropriate to the target environment.
- Keep incident resolution opt-in and distinct from recovery evidence; bound observability queries
  and redact sensitive provider output before it becomes durable.
- Keep registry indexes and snapshots Markdown-first; verify remote releases before extraction,
  validate every contained pack before copying, persist provenance, and preserve
  project-over-user-over-bundled precedence.
- Keep registry trust public-only and Markdown-first; preserve project-over-user key precedence and
  never allow explicit key input to bypass a persisted revocation.
- Keep registry updates preview-first, forward-only, authenticated, transactional, and historically
  auditable; never refresh installed packs implicitly.
- Keep pack dependencies versioned, cross-kind, scope-local, cycle-free, and resolved before writes;
  never replace a dependency when that would break an installed consumer.
- Keep catalog pack provenance installer-owned and checksum-pinned; keep pack updates preview-first,
  forward-only, composition-safe, and protective of local amendments.
- Keep pack update histories continuous and pack composition locks deterministic; refresh locks only
  after successful managed mutations or an explicit reviewed lock command.
- Keep pack removal preview-first and rollback-protected; block reverse dependents and durable
  references, require explicit unused-dependency pruning, and preserve a scope-level audit record.
- Treat Scrum and Kanban as bundled examples, never as privileged core workflows.
- Preserve recursive swarm cycle checks and configured delegation depth.
- Preserve explicit child-work acceptance and reference-based result collection across swarms.
- Keep usage accounting provider-neutral, append-only, evidence-backed, and bounded by inherited
  work budgets; external runtimes measure consumption and Agora validates submitted amounts.
- Prefer small, reviewable changes and abstractions backed by a concrete lifecycle requirement.
