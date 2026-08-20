# Spec tooling and runtime resilience

Agora provides advisory specification tools without weakening Method Pack gates. Clarifications,
checklists, consistency reports, and generated Gherkin never satisfy acceptance criteria, grant an
approval, or transition work by themselves.

These commands are cross-method capabilities: they work in any Method Pack whose assigned role
grants the corresponding action. They are optional by default. A project can make a generated
`consistency-report` or `gherkin-feature` mandatory by declaring that artifact kind on the work or
in a gate. Clarifications and checklists remain non-binding even when a role may create them.

## Clarify intent

```bash
agora work clarify --swarm delivery --work payment-retry --by spec-owner
```

The assigned actor's configured runtime returns at most five targeted questions. Agora appends them
to `clarifications.md` using schema `agora/clarifications/v1`; unresolved answers remain empty. An
authenticated actor first uses `work clarify-prepare`, exports and signs the action authorization,
then applies it with `agora action apply`.

For a `generic` integration, pass `--runner "company-agent advise"`. Agora exposes the reviewed
prompt through the temporary file path in `AGORA_ADVISORY_PROMPT`; the runner must return the
command's documented JSON shape on standard output:

```json
{"questions": [{"question": "Which timeout applies?", "answer": null}]}
```

The array may contain zero to five entries. Questions must be non-empty; answers are strings or
`null`.

## Maintain a non-binding checklist

```bash
agora work checklist add --swarm delivery --work payment-retry \
  --title "Specification quality" \
  --item "Failure behavior is explicit" \
  --item "Every term has one meaning" --by spec-owner

agora work checklist check --swarm delivery --work payment-retry \
  --checklist specification-quality --item 1 --by spec-owner
```

Each checklist is a Markdown task list under `checklists/`. Checking an item is attributed and
durable, but checklist state is intentionally absent from gate evaluation. Authenticated actors use
the corresponding `add-prepare` or `check-prepare` subcommand.

## Verify consistency and generate Gherkin

```bash
agora work verify-consistency --swarm delivery --work payment-retry --by developer
agora work gherkin --swarm delivery --work payment-retry --by developer
```

The consistency command reads registered `repo://` artifacts, writes a bounded Markdown report,
registers it as `consistency-report`, and appends `consistency-check` evidence. The Gherkin command
writes one `.feature` file per acceptance criterion and registers every file as a
`gherkin-feature`. Agora generates but does not execute features. Authenticated actors use
`verify-consistency-prepare` or `gherkin-prepare` before applying the signed intent.

Generic consistency runners return `{"result":"success|failure","report":"...Markdown..."}`.
Generic Gherkin runners return a `features` object whose keys exactly match the criterion ids and
whose values contain a complete `Feature`, `Scenario`, `Given`, `When`, and `Then` document.
Consistency input from registered artifacts is bounded to 256 KiB and excludes prior consistency
reports, preventing recursive self-review and unbounded prompts.

## Trace provenance and detect stale output

Every generated clarification row, consistency report, and Gherkin feature records a canonical
SHA-256 digest of the exact work inputs used to produce it. The digest covers the relevant title,
description, acceptance criteria, and bounded artifact contents; criterion stage changes do not
invalidate content that was generated from the same criterion text.

```bash
agora work traceability --swarm delivery --work payment-retry
agora validate
```

`work traceability` maps every criterion to its stages, generated feature, directly linked evidence,
and shared artifacts. It also compares recorded and current digests. `agora validate` reports stale
generated output as a warning, leaving gates and work state unchanged. Regenerate the affected
advisory output after reviewing the changed inputs. Older generated records without a digest remain
readable and are reported with `clarifications.provenance-missing` or
`artifact.provenance-missing`.

Regenerating Gherkin updates each criterion's existing feature in place and does not duplicate its
artifact row. A consistency run creates a new timestamped report and evidence record so review
history remains append-only.

## Configure runtime fallbacks

```bash
agora actor runtime --actor developer \
  --integration codex --provider openai --model primary \
  --fallback claude:anthropic:fallback-model
```

Fallback order is durable actor configuration. A fresh session chooses the first runtime with an
available executable and skips a matching runtime after a recognized quota or rate-limit response.
An ordinary agent failure stays on that runtime. The selected integration, provider, and model are
recorded on the session and Activity Ledger. Use `--clear-fallbacks` to remove only the fallback
list.

## Render the aggregate board

```bash
agora status --board
```

The board renders one fixed-width frame per swarm, using that swarm's Method Pack work states. The
plain `agora status` JSON contract remains unchanged.
