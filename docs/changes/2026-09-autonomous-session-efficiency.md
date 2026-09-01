# Autonomous session efficiency

Agora now keeps autonomous execution context and durable output proportional to the selected work
item instead of project history.

- Session context omits the project Activity Ledger and full event streams, embeds a compact work
  snapshot token, omits unrelated environment policies, and permits only targeted expansion.
- Failed-session retries record their source and orient from `SUMMARY.md`, not the provider
  transcript in `RESULT.md`.
- New session results default to 128 KiB and can be bounded from 64 to 256 KiB while retaining
  original stream sizes, final output, recent diagnostics, and an explicit truncation marker.
- Authoritative Codex `tokens used` telemetry becomes an append-only, session-backed usage record.
- Aggregate work reads use shared locks, and repeated compact inspections can reuse a
  `snapshot_token` for a minimal unchanged response without assembling the projection.
- Provider-neutral execution profiles map `efficient`, `balanced`, and `complex` to adapter effort;
  native CLI sessions are ephemeral and suppress color noise.
- `agora validate --summary` groups repeated issues and bounds representative paths.
- The `agora-execute` adapter requires quiet commands, narrow ranges, targeted tests, and bounded
  displayed tool output.

The engine remains provider-neutral: it does not hard-code a premium or economy model and does not
estimate usage when a runtime supplies no authoritative counter. Runtime model selection stays in
project and actor configuration; the profile only communicates intended effort to each adapter.
