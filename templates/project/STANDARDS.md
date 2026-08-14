---
schema: "agora/standards/v1"
project: "{{PROJECT_NAME}}"
standards: ["conventional-commits/v1.0.0"]
---

# Project standards

## Conventional Commits 1.0.0

Every Git commit created for governed work must use:

```text
<type>[optional scope][!]: <description>

[optional body]

[optional footer(s)]
```

Use `feat` for a new feature and `fix` for a bug fix. Other descriptive types such as `docs`, `test`,
`refactor`, `build`, `ci`, and `chore` are allowed. Mark breaking changes with `!` before `:` or an
uppercase `BREAKING CHANGE:` footer. A body or footer must begin after a blank line.

Use the governed `repository/commit` Tool Pack operation when the acting role has
`repository.write`. Agora validates its `message` input before Git is invoked. Project amendments may
restrict types or scopes further, but must not weaken the Conventional Commits 1.0.0 structure.
