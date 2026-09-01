---
schema: "agora/tool/v1"
id: "repository"
name: "Local Git repository"
version: "1.0.0"
dependencies: []
category: "repository"
executable: "git"
authentication-reference: "local-git-configuration"
timeout-seconds: 300
max-output-bytes: 1048576
---

# Local Git repository

Provides governed, shell-free access to selected Git operations in the current project. Repository
credentials and signing configuration remain under Git and operating-system control.
