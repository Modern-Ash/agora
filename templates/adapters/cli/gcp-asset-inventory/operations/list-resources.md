---
schema: "agora/tool-operation/v1"
id: "list-resources"
name: "List Google Cloud assets"
capability: "cloud.read"
risk: "read"
arguments: ["asset","search-all-resources","--scope={environment}","--limit=100","--format=json(name,assetType,project,displayName,location,state)"]
inputs: ["environment"]
result-kind: "cloud-resource-list"
---

# List Google Cloud assets

Returns a bounded JSON projection of resources visible within the explicit scope.
