# Knowledge-base integrations

Agora includes a provider-neutral `knowledge-base` Tool Pack for searching, reading, drafting,
updating, publishing, and archiving external documentation. A reviewed adapter can connect the same
contract to Confluence, Notion, a documentation portal, or an internal knowledge service.

## Stable operation contract

New projects receive `.agora/tools/knowledge-base` with this interface:

| Operation | Capability | Risk | Inputs | Result kind |
| --- | --- | --- | --- | --- |
| `search` | `docs.read` | read | `space`, `query` | `document-list` |
| `view` | `docs.read` | read | `document` | `documentation` |
| `create` | `docs.write` | write | `space`, `parent`, `title`, `body` | `documentation` |
| `update` | `docs.write` | write | `document`, `title`, `body` | `documentation` |
| `publish` | `docs.publish` | write | `document` | `documentation-publication` |
| `archive` | `docs.archive` | destructive | `document` | `documentation-archive` |

The default executable is `docsctl`, a stable team-controlled adapter name. Its structured interface
includes commands such as:

```text
docsctl page search --space ENG --query "delivery architecture" --output json
docsctl page view DOC-42 --output json
docsctl page publish DOC-42 --output json
```

Agora passes each argument directly without a shell. The adapter maps stable space and document
identities to provider-specific sites, databases, pages, versions, or publication states.

Existing projects are not rewritten by a CLI update. Install the bundled pack explicitly:

```bash
agora pack install \
  --kind tool \
  --id knowledge-base \
  --registry agora-bundled \
  --scope project
agora validate
```

Installation refreshes `PACKS.lock.md` but preserves local Method Pack permissions.

## Default authority

Bundled methods grant documentation authority by responsibility:

| Role type | Granted capabilities |
| --- | --- |
| Product Owner or Service Request Manager | `docs.read`, `docs.write` |
| Developer or Delivery | `docs.read`, `docs.write` |
| Scrum Master or Flow Manager | `docs.read` |
| Every bundled role | no `docs.publish` or `docs.archive` |

Drafting remains part of ordinary delivery, while publication and archival require an explicit local
policy decision. Installing the pack grants nothing by itself.

## Prepare and launch

Prepare a search without requiring the provider executable or network access:

```bash
agora tool invoke \
  --id find-delivery-guides \
  --tool knowledge-base \
  --operation search \
  --actor facilitator \
  --swarm release \
  --work knowledge-update \
  --input space=ENG \
  --input query="delivery architecture"
```

Preparation validates actor identity, assignment, capability, inputs, and optional approval policy,
then persists `RUN.md`. Add `--launch` only where the reviewed `docsctl` adapter and its external
authentication are available. Agora captures output, errors, status, and result kind in `RESULT.md`.

Document titles and bodies are durable Tool Pack inputs. Teams must not pass secrets or content that
their repository policy forbids storing in Agora and Git. Credentials always remain in the provider
CLI, workload identity, keychain, or secret manager.

## Guard publication

Grant `docs.publish` only to the intended local Method Pack role. A team may then require an approval
on `operations/publish.md`:

```markdown
---
schema: "agora/tool-operation/v1"
id: "publish"
name: "Publish a document"
capability: "docs.publish"
risk: "write"
arguments: ["page","publish","{document}","--output","json"]
inputs: ["document"]
approval-role: "product-owner"
result-kind: "documentation-publication"
---
```

Review local pack amendments and refresh the lock:

```bash
agora pack lock --scope project
agora validate
```

The publisher must have `docs.publish`, and the selected work must contain approval from the declared
role. Archival should use its separate `docs.archive` capability and normally a stronger policy
because it can remove discoverability or access.

## Adapt Confluence or another provider

A reviewed `docsctl` wrapper should:

1. accept only the declared `page` operations and flags;
2. map stable space, parent, and document identities explicitly;
3. convert the stable body representation to the provider's supported format;
4. preserve or reject version conflicts instead of silently overwriting concurrent edits;
5. invoke child CLIs with argument arrays rather than shell strings;
6. return machine-readable output and preserve non-zero provider exit codes;
7. resolve credentials externally and redact sensitive provider output.

For Confluence, a wrapper may map spaces, page ids, parents, drafts, and current versions. For Notion,
it may map spaces to approved databases or parent pages. Provider formatting, pagination, and API
details belong in the adapter or a provider-specific Tool Pack, never in Agora's kernel.

If the provider needs a different interface, publish a team pack with reviewed argument arrays, a
new semantic version, and the same provider-neutral capabilities.

## State ownership

Agora owns actor authority, approvals, work evidence, Tool Runs, and local Markdown history. The
knowledge provider owns remote page content and publication state. A published remote document does
not automatically satisfy a required artifact or transition work; record the returned document URI
as an Agora artifact or evidence reference when the active Method Pack requires it.

Run the executable publication example:

```bash
uv run python samples/knowledge-base/run.py
```
