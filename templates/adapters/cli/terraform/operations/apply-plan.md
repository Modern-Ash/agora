---
schema: "agora/tool-operation/v1"
id: "apply-plan"
name: "Apply a saved Terraform plan"
capability: "cloud.deploy"
risk: "write"
arguments: ["-chdir={environment}","apply","-input=false","-no-color","{plan}"]
inputs: ["plan","environment"]
result-kind: "cloud-deployment"
---

# Apply a saved Terraform plan

Applies exactly one previously saved plan. Bundled roles do not receive `cloud.deploy` authority.
