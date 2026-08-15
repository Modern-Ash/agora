---
schema: "agora/tool-operation/v1"
id: "inspect-resource"
name: "Inspect a Google Cloud asset"
capability: "cloud.read"
risk: "read"
arguments: ["asset","search-all-resources","--scope={environment}","--query=name={resource}","--limit=1","--format=json(name,assetType,project,displayName,location,state)"]
inputs: ["resource","environment"]
result-kind: "cloud-resource"
---

# Inspect a Google Cloud asset

Searches for one exact full resource name and returns a bounded JSON projection.
