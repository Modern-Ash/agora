---
schema: "agora/tool-operation/v1"
id: "destroy-resource"
name: "Destroy a targeted Terraform resource"
capability: "cloud.destroy"
risk: "destructive"
arguments: ["-chdir={environment}","destroy","-input=false","-auto-approve","-target={resource}","-no-color"]
inputs: ["resource","environment"]
result-kind: "cloud-destruction"
---

# Destroy a targeted Terraform resource

Destroys one targeted resource and dependencies selected by Terraform. The command is
non-interactive because Agora authority and approvals must be completed before launch. No bundled
role receives `cloud.destroy` authority.
