---
schema: "agora/tool/v1"
id: "terraform"
name: "Terraform CLI adapter"
version: "1.0.0"
dependencies: []
category: "cloud"
executable: "terraform"
version-command: ["version"]
minimum-runtime-version: "1.5.0"
authentication-reference: "terraform-backend-and-provider-profile"
credential-sources: ["env", "workload-identity"]
provider: "hashicorp"
transport: "cli"
implements: "cloud-infrastructure"
---

# Terraform CLI adapter

Translates Agora's provider-neutral cloud capabilities into structured Terraform CLI commands. The
`environment` input is a reviewed Terraform root-module directory. Backend and provider
authentication remain in Terraform and its workload environment.

Saved plan files may contain sensitive values. Agora records the plan path but does not copy the
binary plan into Markdown.
