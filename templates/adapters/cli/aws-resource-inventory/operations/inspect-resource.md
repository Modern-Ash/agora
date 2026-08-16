---
schema: "agora/tool-operation/v1"
id: "inspect-resource"
name: "Inspect an AWS resource tag mapping"
capability: "cloud.read"
risk: "read"
environment-required: true
arguments: ["resourcegroupstaggingapi","get-resources","--resource-arn-list","{resource}","--region","{environment}","--output","json","--no-cli-pager"]
inputs: ["resource","environment"]
result-kind: "cloud-resource"
---

# Inspect an AWS resource tag mapping

Returns the tag mapping for one explicit ARN without calling a service-specific describe operation.
