---
schema: "agora/tool-operation/v1"
id: "plan"
name: "Create a saved Terraform plan"
capability: "cloud.plan"
risk: "read"
environment-required: true
arguments: ["-chdir={environment}","plan","-input=false","-no-color","-out={change}"]
inputs: ["environment","change"]
result-kind: "infrastructure-plan"
---

# Create a saved Terraform plan

Writes the reviewed plan path supplied as `change`. The resulting binary is external sensitive
state and should be stored using the project's protected artifact policy.
