# Contributing to Agora

Agora is experimental. Prefer small changes that remain inspectable after installation.

```bash
npm install
npm run check
npm run example
```

## Rules

- Preserve provider, model, agent, IDE, and cloud independence.
- Do not add an LLM SDK to the core CLI.
- Keep operational state in Markdown and Git, not a parallel database or JSON snapshot.
- Keep adapter-specific output outside Method Packs and domain rules.
- Add tests for capabilities, role actions, transitions, gates, and filesystem behavior.
- Update templates and documentation whenever the installed protocol changes.
- Never persist raw credentials; store only external authentication references.
- Treat humans, AI agents, services, automations, and swarms as compatible actor forms governed by
  role contracts.

Generated `dist`, local `.agora`, and installed agent commands are not committed in this repository.
