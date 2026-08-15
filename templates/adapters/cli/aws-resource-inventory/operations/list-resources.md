---
schema: "agora/tool-operation/v1"
id: "list-resources"
name: "List tagged AWS resources"
capability: "cloud.read"
risk: "read"
environment-required: true
arguments: ["resourcegroupstaggingapi","get-resources","--region","{environment}","--max-items","100","--output","json","--no-cli-pager"]
inputs: ["environment"]
result-kind: "cloud-resource-list"
---

# List tagged AWS resources

Returns at most one hundred tagged or previously tagged resource mappings in the selected Region.
