---
schema: "agora/tool-operation/v1"
id: "add-item"
name: "Add an item to a portfolio project"
capability: "portfolio.write"
risk: "write"
arguments: ["item","add","--owner","{owner}","--project","{project}","--item","{item-url}","--output","json"]
inputs: ["owner","project","item-url"]
result-kind: "portfolio-item"
---

# Add an item to a portfolio project

Adds a reference to an existing external issue or code review.
