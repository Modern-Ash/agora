---
schema: "agora/tool/v1"
id: "cloud-infrastructure"
name: "Cloud infrastructure"
version: "1.0.0"
dependencies: []
category: "cloud"
executable: "cloudctl"
authentication-reference: "cloud-workload-identity"
---

# Cloud infrastructure

Provides a provider-neutral command contract for cloud inspection, change planning, deployment, and
destruction. Configure `cloudctl` as a reviewed wrapper over AWS, Azure, Google Cloud, Terraform,
OpenTofu, Pulumi, or an internal platform. Credentials remain outside Agora.
