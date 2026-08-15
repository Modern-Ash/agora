---
schema: "agora/tool-operation/v1"
id: "inspect-resource"
name: "Inspect a Terraform resource address"
capability: "cloud.read"
risk: "read"
environment-required: true
arguments: ["-chdir={environment}","state","list","{resource}"]
inputs: ["resource","environment"]
result-kind: "cloud-resource"
---

# Inspect a Terraform resource address

Returns matching resource addresses without printing resource attributes or raw state. Detailed
state inspection requires a reviewed wrapper with provider-specific redaction.
