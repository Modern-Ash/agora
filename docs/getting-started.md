# Getting started

This guide creates a governed Scrum swarm in an existing or empty project. Agora stores its protocol
and work state in Markdown. Git is recommended for history and branch isolation, but filesystem-only
operation is supported.

For installation alternatives, upgrades, scope precedence, and deeper configuration, see
[Installation and customization](guides/installation-and-customization.md).

## 1. Install Agora

Agora requires Python 3.11 or newer. From this repository:

```bash
uv sync --extra dev
uv tool install .
agora --help
```

During development, replace `agora` with `uv run agora` to execute the checkout directly.

## 2. Choose an agent environment and lifecycle

Configure defaults once in `~/.agora/config.md`:

```bash
agora configure \
  --integration codex \
  --provider openai \
  --model configured-by-codex \
  --default-method scrum \
  --max-delegation-depth 3
```

The integration selects where portable Agora instructions are installed. Provider and model are
descriptive values for the selected execution environment. Agora does not use them to call an API.
The delegation limit bounds locally linked child-swarm chains and may be set to `0` to disable them.

For Claude or local-model examples, see [LLM environments](guides/llm-environments.md).

## 3. Initialize a project

```bash
mkdir payment-service
cd payment-service
git init
agora init
agora doctor
```

Initialization creates `.agora/` and installs the selected environment adapter. With the Codex
integration, the project also receives `.agents/skills/agora-*/SKILL.md` files.

Inspect the durable configuration before forming a team:

```text
.agora/project.md
.agora/constitution.md
.agora/PROTOCOL.md
.agora/methods/scrum/METHOD.md
.agora/methods/scrum/roles/*.md
.agora/tools/TOOLS.md
.agora/tools/repository/TOOL.md
```

Project policy may make these defaults more restrictive. Credentials never belong in these files.

## 4. Register actors

Actors describe identity, kind, and capabilities. A user actor can be reused across projects; a
project actor exists only in the current workspace.

```bash
agora actor add --scope user \
  --id owner --name "Product Owner" --kind human \
  --capability backlog-management --capability acceptance

agora actor add \
  --id facilitator --name "AI Scrum Master" --kind ai-agent \
  --capability facilitation --capability governance \
  --description "Operates through the configured project LLM environment."

agora actor add \
  --id delivery --name "Delivery Agent" --kind ai-agent \
  --capability implementation
```

An AI actor does not receive authority merely because an LLM is available. Authority comes from a
role assignment whose capability and actor-kind requirements match the actor.

## 5. Form a swarm

```bash
agora swarm create \
  --id payment-api \
  --objective "Deliver an authenticated payment endpoint"

agora swarm assign --swarm payment-api --role product-owner --actor user:owner
agora swarm assign --swarm payment-api --role scrum-master --actor facilitator
agora swarm assign --swarm payment-api --role developer --actor delivery
```

In a Git repository, swarm creation creates and checks out `agora/payment-api` by default. Once every
required role is assigned, the swarm becomes `ready`.

## 6. Create governed work

The Product Owner role permits `work.create`:

```bash
agora work create \
  --swarm payment-api \
  --id authenticated-endpoint \
  --title "Implement authenticated payment endpoint" \
  --description "Reject unauthenticated requests and preserve the public API contract." \
  --by owner \
  --criterion "authentication-required:Unauthenticated requests are rejected" \
  --criterion "contract-preserved:The public API contract remains valid" \
  --required-artifact source-code \
  --required-artifact test-report
```

The Scrum pack creates work in `specified`. Its primary path is:

```text
specified -> planned -> implementing -> reviewing -> verifying -> completed
```

Only declared transition edges can be traversed. Scrum also declares review and verification rework
edges back to `implementing`, with role restrictions and WIP limits on active states.

## 7. Execute and record evidence

Prepare the AI actor's execution context before it changes the project:

```bash
agora start --id payment-delivery --actor delivery \
  --swarm payment-api --work authenticated-endpoint
```

This creates `.agora/sessions/payment-delivery/`. Add `--launch` to run the detected local LLM CLI;
without it, the session can be handed to an IDE, cloud worker, or other external orchestrator.

The assigned Developer can inspect the project through the bundled repository Tool Pack:

```bash
agora tool invoke --id payment-status \
  --tool repository --operation status \
  --actor delivery --swarm payment-api --work authenticated-endpoint \
  --launch
```

The operation requires `repository.read`, which the Scrum Developer role grants. Agora executes Git
without a shell and persists its output under `.agora/tool-runs/payment-status/`.

```bash
agora work transition --swarm payment-api --work authenticated-endpoint \
  --to planned --by delivery
agora work transition --swarm payment-api --work authenticated-endpoint \
  --to implementing --by delivery
agora work transition --swarm payment-api --work authenticated-endpoint \
  --to reviewing --by delivery

agora artifact add --swarm payment-api --work authenticated-endpoint \
  --kind source-code --uri repo://src/payments.py --by delivery
agora artifact add --swarm payment-api --work authenticated-endpoint \
  --kind test-report --uri ci://builds/123/tests --by delivery

agora work transition --swarm payment-api --work authenticated-endpoint \
  --to verifying --by facilitator
agora evidence add --swarm payment-api --work authenticated-endpoint \
  --type test-run --result success --artifact ci://builds/123/tests --by facilitator
```

Artifact URIs are portable references. Agora records them but does not assume a repository host,
CI/CD product, programming language, or cloud provider.

## 8. Accept and complete

```bash
agora work criterion-satisfy --swarm payment-api --work authenticated-endpoint \
  --criterion authentication-required --by owner
agora work criterion-satisfy --swarm payment-api --work authenticated-endpoint \
  --criterion contract-preserved --by owner

agora approval add --swarm payment-api --work authenticated-endpoint \
  --role product-owner --by owner --note "Accepted for completion"

agora work transition --swarm payment-api --work authenticated-endpoint \
  --to completed --by owner
```

The final transition fails without satisfied criteria, every required artifact kind, successful
evidence, Product Owner approval, and permission for the exact edge. A failed gate leaves the work
unchanged.

When an external dependency interrupts delivery, preserve the current method state instead of
inventing a transition:

```bash
agora work block --swarm payment-api --work authenticated-endpoint --by delivery \
  --reason "Waiting for the identity provider contract"
agora work resume --swarm payment-api --work authenticated-endpoint --by facilitator \
  --reason "The identity provider contract is available"
```

See [Interruptions and cancellation](guides/interruptions-and-cancellation.md) for cancellation and
delegation rules.

## 9. Inspect and commit the durable record

```bash
agora status
agora swarm show --swarm payment-api
agora work show --swarm payment-api --work authenticated-endpoint
agora event list --swarm payment-api --work authenticated-endpoint --limit 20
agora validate
git status
git add .agora
git commit -m "record governed payment API delivery"
```

The resulting work directory contains current state and append-only operational records:

```text
.agora/swarms/payment-api/work/authenticated-endpoint/
  WORK.md
  status-changes/<change-id>/STATUS.md
  artifacts.md
  evidence.md
  approvals.md
  events.md
  interactions.md
```

The prepared execution record remains under `.agora/sessions/payment-delivery/`, including its
resolved runtime and compiled context. The governed repository result remains under
`.agora/tool-runs/payment-status/`.

`status` reports active and attention-worthy records. `validate` audits the complete workspace and
returns a nonzero exit status for CI when schemas or cross-record references are invalid.

Continue with the [operations and validation guide](guides/operations-and-validation.md) for query
and CI semantics, the [Scrum delivery guide](guides/scrum-delivery.md) for role semantics and LLM
interaction patterns, or the [Method Pack reference](reference/method-packs.md) to define a different
lifecycle.
