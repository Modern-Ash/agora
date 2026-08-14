---
schema: "agora/tool/v1"
id: "aws-resource-inventory"
name: "AWS resource inventory CLI adapter"
version: "1.0.0"
dependencies: []
category: "cloud"
executable: "aws"
authentication-reference: "aws-cli-profile-or-workload-identity"
provider: "aws"
transport: "cli"
implements: "cloud-infrastructure"
implements-operations: ["list-resources","inspect-resource"]
---

# AWS resource inventory CLI adapter

Implements only the read-only inventory portion of Agora's cloud contract through AWS CLI. The
`environment` input is an AWS Region; account selection and credentials remain in the active AWS
profile or workload identity.

The Resource Groups Tagging API returns tagged or previously tagged resources, not a complete AWS
account inventory. Plan, apply, and destroy are deliberately absent.
