# GitLab CI/CD CLI adapter sample

This sample installs Agora's reviewed `gitlab-ci` adapter, prepares bounded native pipeline list and
inspection commands, and proves that installation grants neither cancellation authority nor a
lossy pipeline-trigger translation.

Run it without credentials or an installed provider CLI:

```bash
uv run python samples/gitlab-ci-cli/run.py
```

The sample prepares commands but does not launch them. Live execution requires GitLab CLI 1.109.0
or newer and an externally authenticated profile or environment. Add `--launch` only after
`agora tool adapter list --check` reports compatible adapter runtimes.

The adapter implements `list-runs`, `view-run`, and `cancel-run`. It requests JSON and bounded list
results, includes job details without CI/CD variables or logs, and keeps cancellation under the
ungranted `ci.cancel` capability. Use a reviewed team wrapper when the neutral pipeline identity,
ref, and parameters must be translated into a GitLab pipeline trigger or deployment workflow.
