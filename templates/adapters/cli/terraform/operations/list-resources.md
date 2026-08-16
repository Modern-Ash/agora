---
schema: "agora/tool-operation/v1"
id: "list-resources"
name: "List Terraform state resources"
capability: "cloud.read"
risk: "read"
environment-required: true
arguments: ["-chdir={environment}","state","list"]
inputs: ["environment"]
result-kind: "cloud-resource-list"
---

# List Terraform state resources

Lists the resource addresses managed by the configured state backend.
