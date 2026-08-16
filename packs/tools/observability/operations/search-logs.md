---
schema: "agora/tool-operation/v1"
id: "search-logs"
name: "Search service logs"
capability: "observability.read"
risk: "read"
arguments: ["logs","search","--service","{service}","--window","{window}","--query","{query}","--output","json"]
inputs: ["service","window","query"]
result-kind: "log-report"
---

# Search service logs

Returns a bounded log search whose provider adapter must redact sensitive values.
