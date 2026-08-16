---
schema: "agora/tool-operation/v1"
id: "add-item"
name: "Add an item to a GitHub Project"
capability: "portfolio.write"
risk: "write"
arguments: ["project","item-add","{project}","--owner","{owner}","--url","{item-url}","--format","json"]
inputs: ["owner","project","item-url"]
result-kind: "portfolio-item"
---

# Add an item to a GitHub Project

Adds an existing issue or Pull Request URL to one project.
