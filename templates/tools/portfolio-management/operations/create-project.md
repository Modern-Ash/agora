---
schema: "agora/tool-operation/v1"
id: "create-project"
name: "Create a portfolio project"
capability: "portfolio.write"
risk: "write"
arguments: ["project","create","--owner","{owner}","--title","{title}","--output","json"]
inputs: ["owner","title"]
result-kind: "portfolio-project"
---

# Create a portfolio project

Creates one portfolio project. Owner roles receive this capability in bundled Method Packs.
