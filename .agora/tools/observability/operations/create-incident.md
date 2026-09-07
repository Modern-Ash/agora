---
schema: "agora/tool-operation/v1"
id: "create-incident"
name: "Create an incident"
capability: "incident.write"
risk: "write"
arguments: ["incident","create","--service","{service}","--severity","{severity}","--title","{title}","--summary","{summary}","--output","json"]
inputs: ["service","severity","title","summary"]
result-kind: "incident"
---

# Create an incident

Creates an attributable external incident without changing Agora work state.
