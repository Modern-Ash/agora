---
schema: "agora/tool-operation/v1"
id: "archive-item"
name: "Archive a GitHub Project item"
capability: "portfolio.write"
risk: "write"
arguments: ["project","item-archive","{project}","--owner","{owner}","--id","{item}","--format","json"]
inputs: ["owner","project","item"]
result-kind: "portfolio-item"
---

# Archive a GitHub Project item

Archives one project item without deleting the underlying issue or Pull Request.
