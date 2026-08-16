---
schema: "agora/tool-operation/v1"
id: "create-project"
name: "Create a GitHub Project"
capability: "portfolio.write"
risk: "write"
arguments: ["project","create","--owner","{owner}","--title","{title}","--format","json"]
inputs: ["owner","title"]
result-kind: "portfolio-project"
---

# Create a GitHub Project

Creates one project with an explicit owner and title.
