---
schema: "agora/tool-operation/v1"
id: "update-incident"
name: "Update an incident"
capability: "incident.write"
risk: "write"
arguments: ["incident","update","{incident}","--status","{status}","--summary","{summary}","--output","json"]
inputs: ["incident","status","summary"]
result-kind: "incident"
---

# Update an incident

Adds reviewed status and context to one external incident.
