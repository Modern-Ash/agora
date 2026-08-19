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

## Native GitLab Issues adapter

Install the partial GitLab adapter when the developer already uses `glab`:

```bash
agora tool adapter install --id gitlab-issues --scope project
agora tool adapter list --check
```

It maps `search`, `view`, `comment`, and `transition` to native GitLab issue commands. Search returns
at most fifty open or closed issues as JSON. Transition restricts its dynamic subcommand to `close`
or `reopen`, so `delete`, `update`, and other verbs are rejected before a Tool Run exists. Issue IIDs
use the repository already selected by `glab`; full issue URLs can target another project.

The adapter deliberately omits `create`. Agora's neutral operation requires a stable work-item
`type`, while native `glab issue create` does not accept an equivalent input. A reviewed team wrapper
may normalize an organization-specific type mapping; the bundled adapter does not silently convert
types into labels or discard them. GitLab CLI installation and authentication remain external; see
the official [`glab issue` reference](https://docs.gitlab.com/cli/issue/).

## Native Jira ACLI adapter

Install the reviewed Jira Cloud adapter when Atlassian CLI is part of the developer environment:

```bash
agora tool adapter list --available
agora tool adapter install --id jira --scope project
```

The adapter maps all five operations to `acli jira workitem`. Search uses JQL with a limit and
selected fields; create and comment provide their bodies through non-interactive flags; transition
uses one explicit key and status with `--yes`. ACLI owns Jira site selection and authentication.

The pack may be installed for command preparation when ACLI is absent, but `--launch` then fails
before creating an external process. Agora does not download ACLI or fall back to an MCP server.

## Role authority

Bundled Spec-Driven, Scrum, and Kanban packs grant external work authority separately:

| Role type | Granted capabilities |
| --- | --- |
| Product Owner, Service Request Manager, or Spec Owner | `issue.read`, `issue.write`, `issue.transition` |
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
Inspect the typed run and its bounded provider output without opening the Markdown files manually:

```bash
agora tool result --run move-agora-42
```

The Jira sample launches the exact reviewed adapter contract against a deterministic,
ACLI-compatible local process, including a final read that shows the created issue, comment, and
transition. It demonstrates Agora's complete execution boundary without claiming a Jira Cloud
connection:

```bash
uv run python samples/jira-cli/run.py
```

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

## Credential Source Chain

Every Tool Pack adapter declares an ordered `credential-sources` list in its `TOOL.md` front
matter, chosen from four sources:

| Source | Meaning |
| --- | --- |
| `cli-session` | The provider's own CLI is already logged in (`gh auth login`, `acli`/`twg` site selection, `gcloud auth login`) |
| `env` | A single, provider-derived environment variable — `AGORA_<PROVIDER>_TOKEN` — is set |
| `keychain` | The OS keychain holds the credential (not locally inspectable) |
| `workload-identity` | Ambient identity — an IAM role or OIDC token — applies (not locally inspectable) |

Agora resolves this chain the same way for every provider — it is the one standard connection
pattern across GitHub, GitLab, Jira, Confluence, Terraform, AWS, and GCP — but it never reads,
stores, transmits, or displays the credential value itself. It only reports which source, if any,
currently appears satisfied:

```bash
agora tool credentials --tool jira
```

```json
{
  "tool_id": "jira",
  "resolved_source": "cli-session",
  "checks": [
    {"source": "cli-session", "satisfied": true, "detail": "acli is on PATH; session state is not inspected"}
  ]
}
```

Actual authentication is always performed by the provider's own CLI, environment, keychain, or
workload identity at `--launch` time — Agora only wraps `contract.executable` in a subprocess and
inherits the caller's environment. Adding a new adapter means declaring its `credential-sources` in
`TOOL.md`; it never means adding provider-specific credential-handling code to Agora's core.

## Two sources of truth

Agora owns actor identity, role assignment, lifecycle gates, work evidence, approvals, tool-run
attribution, and its filesystem history. The external system owns its remote ticket data. A ticket
transition does not implicitly transition Agora work, and an Agora work transition does not
implicitly mutate a ticket. Agents must execute both governed actions when synchronization is part
of the team's protocol.

This separation prevents a provider outage or vendor migration from making the local governance
record unreadable. Git remains the review and synchronization layer for Agora's Markdown state.

Run the provider-neutral executable adapter example:

```bash
uv run python samples/work-management/run.py
```
