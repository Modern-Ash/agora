---
schema: "agora/tool/v1"
id: "gcp-asset-inventory"
name: "Google Cloud Asset Inventory CLI adapter"
version: "1.0.0"
dependencies: []
category: "cloud"
executable: "gcloud"
authentication-reference: "gcloud-active-account-or-workload-identity"
provider: "google-cloud"
transport: "cli"
implements: "cloud-infrastructure"
implements-operations: ["list-resources","inspect-resource"]
---

# Google Cloud Asset Inventory CLI adapter

Implements only read-only cloud inventory through `gcloud asset search-all-resources`. The
`environment` input is an explicit project, folder, or organization scope. Authentication remains in
the active gcloud account or workload identity.

Plan, apply, and destroy are deliberately absent.
