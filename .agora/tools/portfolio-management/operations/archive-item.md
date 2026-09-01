---
schema: "agora/tool-operation/v1"
id: "archive-item"
name: "Archive a portfolio item"
capability: "portfolio.write"
risk: "write"
arguments: ["item","archive","--owner","{owner}","--project","{project}","--item","{item}","--output","json"]
inputs: ["owner","project","item"]
result-kind: "portfolio-item"
---

# Archive a portfolio item

Archives one project item without deleting its authoritative issue or code review.
