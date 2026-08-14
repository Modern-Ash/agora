# Conventional Commits

Agora adopts [Conventional Commits 1.0.0](https://www.conventionalcommits.org/en/v1.0.0/) as the
default repository-history standard for governed work. The rule is language-, LLM-, Git-host-, and
development-process-agnostic.

## Project contract

Every initialized project contains `.agora/STANDARDS.md`. The constitution and collaboration
protocol require actors to read it, and generated session context includes it in required reading.
`agora validate` fails when the standards document is missing, has the wrong schema, or does not
enable `conventional-commits/v1.0.0`.

The required structure is:

```text
<type>[optional scope][!]: <description>

[optional body]

[optional footer(s)]
```

Use `feat` for a feature and `fix` for a bug fix. The specification permits other descriptive types;
Agora does not impose a closed list. A breaking change uses `!` before the colon or an uppercase
`BREAKING CHANGE:` footer. Bodies and footers begin after a blank line.

Examples:

```text
feat(governance): validate repository commit messages
fix(upgrade): preserve customized tool operations
docs: explain project standards
feat(protocol)!: require explicit release evidence
```

## Governed commit operation

The bundled Git Tool Pack declares:

```markdown
arguments: ["commit","-m","{message}"]
inputs: ["message"]
input-rules: {"message":"conventional-commits/v1.0.0"}
```

After explicitly staging the intended files, an assigned role with `repository.write` can run:

```bash
agora tool invoke --id governed-commit \
  --tool repository --operation commit \
  --actor developer --swarm delivery \
  --input message="feat(api): add payment authorization" \
  --launch
```

Agora validates the message before creating `RUN.md` or invoking Git. Invalid input therefore leaves
neither repository history nor a prepared tool-run record. Git still owns staging, author identity,
signing, hooks, and repository credentials.

## Reusable input rules

`input-rules` is part of the provider-neutral Tool Pack operation contract. Each key must name a
declared input and each value must identify a validator registered by the Agora core. Unknown inputs
and unknown rule identifiers make the Tool Pack invalid. This allows standards to be enforced before
an external command runs without placing a Git SDK or shell parser in the core.

The first registered rule is `conventional-commits/v1.0.0`. Future rules must have stable versioned
identifiers and deterministic local validation.

## Project restrictions

A project may restrict commit types or scopes further through a reviewed amendment or a custom Tool
Pack operation. It must retain the base Conventional Commits structure. Do not edit a generated agent
adapter to weaken the rule; portable commands, project standards, Tool Pack validation, and adapters
must describe the same policy.
