---
schema: "agora/tool/v1"
id: "work-management"
name: "External work management"
version: "1.0.0"
dependencies: []
category: "issue-tracker"
executable: "workctl"
authentication-reference: "work-management-cli-profile"
---

# External work management

Provides a stable, provider-neutral command contract for issue trackers and work-management
systems. Configure `workctl` as a reviewed wrapper over Jira, Linear, an internal service, or any
other provider CLI. Authentication remains outside Agora.
