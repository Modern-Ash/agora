# AI-native SDLC controls

Agora provides provider-neutral contracts for five operating loops that become important when AI
actors participate continuously: intent, evaluations and reviews, runtime guardrails, event
triggers, production control bands, and delivery metrics. Core persists and validates decisions; it
does not call an LLM, execute a webhook action, or replace CI and runtime isolation.

## 1. Start from reviewed intent

Capture the problem and desired outcome before creating implementation work:

```bash
agora intent add --id reduce-api-errors --author product:ana \
  --problem "Customers see elevated API errors" \
  --outcome "Restore the reviewed error budget" \
  --affected-system api --constraint "No standing production credentials" \
  --open-question "Which deployment introduced the regression?" \
  --source incident://INC-42

agora intent decide --id reduce-api-errors --decision accepted \
  --by product:owner --reason "The problem, boundary, and outcome are reviewable"
```

Intent remains a separate governance record. Acceptance does not silently create work or grant an
agent authority.

## 2. Gate changes with evaluations and structured reviews

Evaluation suites describe real accepted cases and the paths that make them relevant. An external
runner executes the cases and records the aggregate result with evidence:

```bash
agora eval suite-add --id agent-regression \
  --case create-safe-api --case preserve-auth --minimum-pass-rate 100 \
  --trigger-path '.agents/**' --trigger-path '.agora/methods/**'

agora eval impacted --path .agents/reviewer.md
agora eval run-record --id eval-20260825 --suite agent-regression \
  --passed 2 --total 2 --evidence ci://agent-evals/20260825
```

`eval run-record` exits non-zero when the suite threshold is missed, so CI can use it as a quality
gate. The recorded counts are supplied by the runner; Agora never claims to have executed the tests.

Store review results as queryable findings instead of prose-only comments:

```bash
agora review finding-add --id auth-001 --swarm delivery --work safe-api \
  --pass security --severity high --policy secure-api/v1 \
  --summary "Endpoint lacks an authorization check" --location src/api.py:42

agora review finding-decide --id auth-001 --decision resolved \
  --by security:reviewer --reason "Authorization middleware is enforced"
```

A waiver is explicit (`--decision waived`) and requires the deciding actor and reason.

## 3. Put deterministic guardrails in runtime hooks

Register project policy, then call `guardrail check` from an agent's pre-action hook:

```bash
agora guardrail add --id protected-runtime \
  --protect-path '.env*' --protect-path 'generated/**' \
  --deny-command 'git reset --hard*' --deny-command 'curl *production*'

agora guardrail check --action file-edit --target .env.production
agora guardrail check --action command --target 'git reset --hard HEAD'
```

A blocked decision exits non-zero and names every matching guardrail. This is a deterministic hook
contract, not universal process mediation: the external agent runtime must invoke it before the
action and still run inside an appropriate filesystem/network sandbox.

## 4. Route external events idempotently

Triggers convert a webhook-shaped event into durable action intents:

```bash
agora trigger add --id merged-to-staging --event pull-request.merged \
  --action prepare-deployment --parameter environment=staging

agora trigger ingest --id github-evt-42 --event pull-request.merged \
  --dedupe-key github:repo:pr:42:sha:abc --payload sha=abc
```

Replaying the same dedupe key and payload returns the original event. Reusing the key with a
different payload fails. Matching only proposes the configured action; a controller must apply the
normal Agora permissions, gates, and approvals before executing it.

## 5. Close the production feedback loop and measure it

Control bands classify an observed metric deterministically. A severe breach creates a draft intent
linked back to the finding, never an automatic production mutation:

```bash
agora control-band add --id api-errors --metric api.5xx-rate \
  --mean 1 --standard-deviation 0.5 --diagnose-sigma 2 --propose-sigma 3

agora control-band evaluate --band api-errors --id sample-20260825 \
  --value 3 --author automation:observability
```

Use the aggregate report in CI, operations, or a dashboard:

```bash
agora metrics
```

The report derives transition and rework counts, first-pass rate, average cycle and human-wait
times, evaluation pass rate, open high-severity findings, intent decisions, and control-band
findings from durable records. Empty samples are reported as `null`, not as invented success.

## Stored records and validation

The contracts are Markdown-first under `.agora/intents`, `.agora/evaluations`, `.agora/reviews`,
`.agora/guardrails`, `.agora/triggers`, and `.agora/control-bands`. `agora validate` loads every
record and reports malformed schemas alongside the existing project, Method Pack, and work checks.
