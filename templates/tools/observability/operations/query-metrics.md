---
schema: "agora/tool-operation/v1"
id: "query-metrics"
name: "Query service metrics"
capability: "observability.read"
risk: "read"
arguments: ["metrics","query","--service","{service}","--window","{window}","--query","{query}","--output","json"]
inputs: ["service","window","query"]
result-kind: "metric-report"
---

# Query service metrics

Returns a bounded provider-neutral metric query result.
