# Operations and validation

Agora keeps operational state in Markdown, but daily users and automation should not need to scan
every directory manually. Query commands read the same files used by lifecycle operations and emit
deterministic views without creating a second state store. A human terminal receives a concise,
colored view; pipes, redirections, IDEs, and process capture receive the same data as structured JSON
automatically. No output-format flag is required.

```mermaid
flowchart LR
    C[Same Agora command] --> T{stdout is a terminal?}
    T -->|yes| H[Human view with color and hierarchy]
    T -->|no| J[Complete deterministic JSON]
    H --> S[Filesystem and Git remain the source of truth]
    J --> S
```

## Project status

Run a compact project-wide summary from the project or with the global project selector:

```bash
agora status
agora --project /path/to/project status
```

The result includes the selected integration, default Method Pack, current Git branch, domain
counts, lifecycle and operational status distributions, and attention lists. Attention currently
identifies forming swarms, active and blocked work, open delegations, unfinished or failed sessions,
and failed tool runs.

`status` is a read operation. It does not repair records, advance work, or infer completion.

## Domain queries

Every list command returns records in deterministic filesystem order. They are rendered for a
terminal and remain JSON when captured or piped:

```bash
agora actor list
agora actor list --scope project
agora method list
agora tool list
agora tool runs --status failed
agora swarm list
agora swarm list --status running
agora swarm handoffs --swarm delivery
agora work list
agora work list --swarm delivery --state reviewing
agora work list --swarm delivery --operational-status blocked
agora work status-changes --swarm delivery --work payment-api
agora delegation list --status accepted
agora delegation list --status cancelled
agora delegation status-changes --delegation specialist-task
agora session list --status prepared
```

Filters match persisted values exactly. An empty machine result is an empty JSON array, not an
error; the terminal view instead reports that no items were found.

## Event inspection

Project, swarm, and work event files use the same timestamped record shape. Query the most recent
events across the project:

```bash
agora event list --limit 20
```

Narrow the result to a swarm, one work item, or an exact event type:

```bash
agora event list --swarm delivery --limit 20
agora event list --swarm delivery --work payment-api
agora event list --type delegation.collected
```

`--work` requires `--swarm`. Results are ordered by their ISO timestamp and include their durable
scope and source path.

## Environment check versus full validation

`agora doctor` is a shallow installation check. It reports whether the project, selected adapter,
default method, tool policy, repository Tool Pack, delegation setting, and Git environment are
available.

`agora validate` is a complete integrity audit:

```bash
agora validate
```

It checks:

- Required project documents and schema identifiers.
- Portable agent commands and Codex, Claude, or generic adapter completeness and consistency.
- Method Pack graphs, roles, gates, WIP definitions, and project default selection.
- Tool Pack operations, inputs, risks, and result contracts.
- Project standards and registered Tool Pack input rules, including Conventional Commits 1.0.0.
- Actor documents, ids, kinds, capabilities, and referenced user actors.
- Swarm identity, status, assignments, role compatibility, recursive cycles, and depth.
- Work identity, owning swarm, lifecycle and operational states, criteria, companion registers, WIP,
  interruption history, and derived swarm state.
- Handoff identities, roles, actors, and optional work references.
- Delegation parent and child records, attribution, lifecycle links, interruption sequence, and
  collected results.
- Session references, roles, context files, and runtime metadata.
- Tool run references, operation contracts, and terminal result documents.
- Project, swarm, and work event syntax and timestamps.

Validation continues after an invalid record so one run can report multiple independent issues. The
The captured JSON response contains `checked` counts and issues with `severity`, stable `code`, `path`, and
`message` fields.

Errors set `ok` to `false` and make the CLI exit with status `1`. Warnings remain visible but do not
fail validation. A valid workspace exits with status `0`, making the command suitable for CI:

```bash
agora validate > agora-validation.json
```

The validator never rewrites files. Repair remains an explicit, reviewable change to the Markdown
source of truth.

Run the [operational query sample](../../samples/operational-query/README.md) for an executable
workspace summary and validation report.

To verify the framework repository, every bundled sample, and the built distributions together, use
the [complete verification guide](verification.md).
