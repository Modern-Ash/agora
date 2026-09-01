---
schema: "agora/tool/v1"
id: "ci-cd"
name: "Continuous integration and delivery"
version: "1.0.0"
dependencies: []
category: "ci"
executable: "cictl"
authentication-reference: "ci-cd-cli-profile"
---

# Continuous integration and delivery

Provides a provider-neutral command contract for inspecting and controlling CI/CD systems. Configure
`cictl` as a reviewed wrapper over GitHub Actions, GitLab CI/CD, Jenkins, or an internal platform.
Authentication and secrets remain outside Agora.
