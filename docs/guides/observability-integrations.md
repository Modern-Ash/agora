# Observability integrations

Agora includes a provider-neutral `observability` Tool Pack for service health, metrics, logs, and
incident records. A reviewed `observectl` adapter can connect Datadog, Grafana, cloud monitoring,
an incident platform, or internal services without adding vendor SDKs to the kernel.

## Operation contract

| Operation | Capability | Risk | Inputs | Result kind |
| --- | --- | --- | --- | --- |
| `service-health` | `observability.read` | read | `service`, `environment` | `service-health` |
| `query-metrics` | `observability.read` | read | `service`, `window`, `query` | `metric-report` |
| `search-logs` | `observability.read` | read | `service`, `window`, `query` | `log-report` |
| `create-incident` | `incident.write` | write | service, severity, title, summary | `incident` |
| `update-incident` | `incident.write` | write | incident, status, summary | `incident` |
| `resolve-incident` | `incident.resolve` | write | incident, resolution | `incident-resolution` |

New projects receive the pack automatically. Existing projects install it explicitly:

```bash
agora pack install --kind tool --id observability \
  --registry agora-bundled --scope project
agora validate
```

Developer, Delivery, Scrum Master, and Flow Manager roles receive `observability.read` and
`incident.write`. No bundled role receives `incident.resolve`; closing an incident requires a local
authority decision.

## Query and declare

```bash
agora tool invoke --id api-health \
  --tool observability --operation service-health \
  --actor developer --swarm incident-response --work restore-api \
  --input service=api --input environment=production --launch

agora tool invoke --id declare-api-incident \
  --tool observability --operation create-incident \
  --actor facilitator --swarm incident-response --work restore-api \
  --input service=api --input severity=high \
  --input title="API errors" --input summary="Error threshold exceeded" --launch
```

Every input is durable. Query windows must be bounded, queries must not embed credentials, and the
adapter must redact personal data, tokens, and sensitive payloads before logs reach `RESULT.md`.

## Guard resolution

Grant `incident.resolve` to the intended local role and add an approval role to
`operations/resolve-incident.md`. After reviewing the amendment, run:

```bash
agora pack lock --scope project
agora validate
```

The resolving actor then needs both the capability and the selected work's required approval.
Project protocol should also require recovery evidence, such as healthy service status and bounded
metric results, before allowing lifecycle completion. Resolving the external incident alone does not
prove recovery and does not transition Agora work.

## Adapter requirements

A reviewed `observectl` wrapper should:

1. map stable service and environment names to allowlisted provider scopes;
2. enforce bounded metric and log windows;
3. reject queries that cross unauthorized tenants or environments;
4. invoke vendor CLIs with argument arrays rather than shell strings;
5. redact secrets, personal data, and sensitive payloads from durable output;
6. preserve non-zero provider exit codes and machine-readable results;
7. keep credentials in workload identity, provider profiles, or a secret manager;
8. keep observability and incident-provider mappings outside Agora's kernel.

Remote health and incident state remain provider-owned. Agora owns actor authority, approvals,
Tool Runs, evidence references, and filesystem history.

Run the executable example:

```bash
uv run python samples/observability/run.py
```
