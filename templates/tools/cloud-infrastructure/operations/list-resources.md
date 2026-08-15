---
schema: "agora/tool-operation/v1"
id: "list-resources"
name: "List cloud resources"
capability: "cloud.read"
risk: "read"
arguments: ["resource","list","--environment","{environment}","--output","json"]
inputs: ["environment"]
result-kind: "cloud-resource-list"
---

# List cloud resources

Returns the resources visible in one approved environment.
