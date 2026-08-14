---
schema: "agora/tool-operation/v1"
id: "transition"
name: "Transition a work item"
capability: "issue.transition"
risk: "write"
arguments: ["issue","transition","{issue}","--to","{state}","--output","json"]
inputs: ["issue","state"]
result-kind: "work-item-transition"
---

# Transition a work item

Changes external workflow state. Agora lifecycle transitions remain governed independently by the
active Method Pack.
