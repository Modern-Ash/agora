# Work-management integrations

Agora includes a provider-neutral `work-management` Tool Pack for daily interaction with issue
trackers and backlog systems. The pack governs who may read, create, comment on, or transition
external work. It does not make Jira, Linear, or any external provider the owner of Agora lifecycle
state.

## Stable operation contract

New projects receive `.agora/tools/work-management` with this interface:

| Operation | Capability | Risk | Inputs | Result kind |
| --- | --- | --- | --- | --- |
| `search` | `issue.read` | read | `query` | `work-item-list` |
| `view` | `issue.read` | read | `issue` | `work-item` |
| `create` | `issue.write` | write | `project`, `type`, `title`, `description` | `work-item` |
| `comment` | `issue.write` | write | `issue`, `body` | `work-item-comment` |
| `transition` | `issue.transition` | write | `issue`, `state` | `work-item-transition` |

Existing projects are not rewritten when the CLI is updated. Install the reviewed bundled pack
explicitly, then amend the active local Method Pack roles with only the required capabilities:

```bash
agora pack install \
  --kind tool \
  --id work-management \
  --registry agora-bundled \
  --scope project
agora validate
```

The installation refreshes `PACKS.lock.md`; it does not alter role permissions.

The default executable is `workctl`. This name describes a team-controlled adapter contract, not a
required vendor product. The adapter accepts structured arguments such as:

```text
workctl issue view AGORA-42 --output json
workctl issue create --project AGORA --type Story --title "..." --description "..." --output json
workctl issue transition AGORA-42 --to "In Progress" --output json
```

Agora passes every array element directly to the executable without a shell. The adapter translates
these stable verbs into the selected provider CLI or API client and writes its result to standard
output. A provider migration changes the adapter, not Method Pack permissions or Agora's kernel.

## Native GitHub Issues adapter

When the developer already uses GitHub CLI, install the reviewed adapter directly:

```bash
agora tool adapter list --available
agora tool adapter install --id github-issues --scope project
```

The adapter implements search, view, create, comment, and transition through `gh`. Its transition
state occupies a native subcommand position, so `input-values` restricts it to `close` or `reopen`.
Any other value is rejected before a Tool Run exists. Repository and authentication selection remain
in the existing GitHub CLI profile, and installation does not alter role authority.

## Role authority

Bundled Scrum and Kanban packs grant external work authority separately:

| Role type | Granted capabilities |
| --- | --- |
| Product Owner or Service Request Manager | `issue.read`, `issue.write`, `issue.transition` |
| Scrum Master or Flow Manager | `issue.read` |
| Developer or Delivery | `issue.read` |

Installing a Tool Pack never grants authority. Invocation still requires an actor assigned to an
active swarm role whose `allowed-tool-capabilities` contains the exact operation capability. Teams
may narrow these defaults or add approval requirements to individual operations.

## Prepare without contacting the provider

An agent in an IDE, CLI, CI worker, or cloud runtime can prepare an attributable command first:

```bash
agora tool invoke \
  --id inspect-agora-42 \
  --tool work-management \
  --operation view \
  --actor delivery-agent \
  --swarm release \
  --work release-candidate \
  --input issue=AGORA-42
```

Preparation validates identity, assignment, role capability, operation inputs, and optional
approval policy. It persists `RUN.md` but does not require `workctl` or network access.

Add `--launch` only when the current environment has the reviewed adapter and its external
authentication:

```bash
agora tool invoke \
  --id move-agora-42 \
  --tool work-management \
  --operation transition \
  --actor product-owner \
  --swarm release \
  --work release-candidate \
  --input issue=AGORA-42 \
  --input state="In Progress" \
  --launch
```

Agora captures command metadata, standard output, standard error, exit code, and result kind under
`.agora/tool-runs/<run-id>`. Project and work event streams receive attributable tool events.

## Adapt Jira or another provider

Keep the bundled pack interface stable and implement one reviewed `workctl` executable. For Jira,
the wrapper may call an approved Jira CLI or an internal HTTP client. For Linear, it may call a
different CLI or service. In either case it should:

1. parse only the declared `issue` subcommands and flags;
2. map provider-specific identifiers and states explicitly;
3. invoke child commands with argument arrays rather than shell strings;
4. return machine-readable output and a non-zero exit code on failure;
5. leave credentials in the provider CLI, keychain, environment, workload identity, or secret
   manager;
6. never echo access tokens into standard output, standard error, or durable arguments.

If the provider cannot implement the stable interface directly, fork the pack into a team registry,
change `executable` and operation argument arrays, increment its semantic version, and install the
reviewed catalog copy. Keep the capabilities provider-neutral.

Do not pass tokens, cookies, private keys, or connection strings through `--input`: Tool Pack inputs
are deliberately persisted. `authentication-reference` is only a non-secret label such as
`jira-cli-work-profile`.

## Two sources of truth

Agora owns actor identity, role assignment, lifecycle gates, work evidence, approvals, tool-run
attribution, and its filesystem history. The external system owns its remote ticket data. A ticket
transition does not implicitly transition Agora work, and an Agora work transition does not
implicitly mutate a ticket. Agents must execute both governed actions when synchronization is part
of the team's protocol.

This separation prevents a provider outage or vendor migration from making the local governance
record unreadable. Git remains the review and synchronization layer for Agora's Markdown state.

Run the executable adapter example:

```bash
uv run python samples/work-management/run.py
```
